import json
from pathlib import Path
import zipfile
import pytest
from opensim_mcp.core import InputError,Settings
from opensim_mcp.bundles import safe_name,export_bundle,verify_bundle,import_bundle
from opensim_mcp.transactions import validate_edits
from opensim_mcp.scene_export import export_scene

ROOT=Path(__file__).resolve().parents[1]/'examples'


@pytest.mark.parametrize('name',['../x','assets/../../x','C:/x','/x','assets\\x','assets/CON.osim','assets/a.','assets/a ','assets/a:b','assets//x','assets/./x'])
def test_zip_paths_reject_windows_escape_and_devices(name):
    with pytest.raises(InputError):safe_name(name)


def test_round_trip_verifies_before_import_and_no_native_execution(tmp_path,monkeypatch):
    scratch=tmp_path/'scratch';scratch.mkdir();cfg=Settings((ROOT,),tmp_path/'results',scratch,None)
    monkeypatch.setattr('opensim_mcp.bundles.environment',lambda _:dict(tool_backend='api',opensim_version='test',python='3.12',mcp='test'))
    bundle=export_bundle(cfg,str(ROOT/'project.json'))
    assert verify_bundle(cfg,bundle['bundle_file'])['valid']
    imported=import_bundle(cfg,bundle['bundle_file']);assert imported['executed'] is False
    p=json.loads(Path(imported['project_path']).read_text(encoding='utf-8'))
    assert all(a['path'].startswith('assets/') for a in p['inputs'].values())
    broken=cfg.results_root/'broken.zip'
    with zipfile.ZipFile(bundle['bundle_file']) as source,zipfile.ZipFile(broken,'w') as target:
        for item in source.infolist():target.writestr(item,source.read(item) if item.filename!='project.json' else b'{}')
    with pytest.raises(InputError,match='hash'):import_bundle(cfg,str(broken))


def test_case_colliding_entries_rejected_before_extraction(tmp_path):
    cfg=Settings((tmp_path,),tmp_path/'results',tmp_path/'scratch',None);path=tmp_path/'bad.zip'
    with zipfile.ZipFile(path,'w') as z:
        for name in ['project.json','PROJECT.json','bundle.json']:z.writestr(name,'{}')
    with pytest.raises(InputError,match='Duplicate'):verify_bundle(cfg,str(path))


def test_edit_transactions_require_revision_and_bounded_explicit_operations():
    with pytest.raises(InputError):validate_edits([],1)
    with pytest.raises(InputError):validate_edits([dict(component_type='body',component_name='x',property_name='mass',value=2)],True)
    with pytest.raises(InputError):validate_edits([dict(code='exec()')],1)


def test_scene_escapes_untrusted_names_and_preserves_native_axes(tmp_path):
    cfg=Settings((tmp_path,),tmp_path/'results',tmp_path/'scratch',None)
    r=export_scene(cfg,dict(name='<script>',revision=4,scope='native geometry',joints=[dict(name='j',parent=[0.,0.,0.],child=[1.,2.,3.])],markers=[]))
    assert '<script>' not in Path(r['html_file']).read_text(encoding='utf-8')
    data=json.loads(Path(r['scene_file']).read_text(encoding='utf-8'));assert data['joints'][0]['child']==[1.,2.,3.]
