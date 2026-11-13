import json
from pathlib import Path
import pytest
from opensim_mcp.core import InputError, Settings
from opensim_mcp.projects import validate_shape, prepare_submission, strict_json, digest, json_bytes
from opensim_mcp.pipeline import inventory, verified_cache, canonical_parameters
from opensim_mcp.quality_report import evaluate, write_reports

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'


def project():
    return {'schema_version':1,'name':'test','inputs':{'model':{'path':str(EXAMPLES/'slider.osim'),'kind':'model'},
        'markers':{'path':str(EXAMPLES/'slider.trc'),'kind':'markers','length_unit':'m'}},
        'stages':[{'id':'ik','workflow':'ik','parameters':{'model_path':'${inputs.model}','marker_path':'${inputs.markers}'}}]}


@pytest.mark.parametrize('change', ['unknown','forward','cycle','type','untracked','bad_ref','duplicate'])
def test_project_rejects_ambiguous_dependencies(change):
    p=project(); stage=p['stages'][0]
    if change=='unknown':p['allowed_roots']=['E:/']
    elif change in {'forward','cycle'}:stage['parameters']['model_path']='${stages.ik.model}'
    elif change=='type':stage['parameters']['model_path']='${inputs.markers}'
    elif change=='untracked':stage['parameters']['model_path']=str(EXAMPLES/'slider.osim')
    elif change=='bad_ref':stage['parameters']['model_path']='${inputs.model}suffix'
    elif change=='duplicate':p['stages'].append(dict(stage))
    with pytest.raises(InputError):validate_shape(p)


def test_duplicate_and_nonfinite_json_rejected():
    for raw in [b'{"a":1,"a":2}',b'{"a":NaN}']:
        with pytest.raises(InputError):strict_json(raw)


def test_manifest_never_grants_access_and_checks_units(tmp_path):
    cfg=Settings((tmp_path,),tmp_path/'results',tmp_path/'temp',None)
    manifest=tmp_path/'project.json'; p=project(); manifest.write_text(json.dumps(p))
    with pytest.raises(InputError,match='outside'):prepare_submission(cfg,str(manifest))
    cfg=Settings((tmp_path,EXAMPLES),tmp_path/'results',tmp_path/'temp',None)
    assert prepare_submission(cfg,str(manifest))['inputs']['model']['sha256']
    p['inputs']['markers']['length_unit']='mm';manifest.write_text(json.dumps(p))
    with pytest.raises(InputError,match='length_unit'):prepare_submission(cfg,str(manifest))


def test_content_key_portable_and_mutation_invalidates(tmp_path):
    a=tmp_path/'a.mot';b=tmp_path/'b.mot';a.write_text('same');b.write_text('same')
    assert canonical_parameters(str(a))==canonical_parameters(str(b))
    b.write_text('different');assert canonical_parameters(str(a))!=canonical_parameters(str(b))


def test_stage_hash_verification_rejects_tamper_and_incomplete(tmp_path):
    entry=tmp_path/'entry';entry.mkdir();(entry/'result.json').write_text('{"outputs":{}}')
    assert verified_cache(entry,'k')[0] is None
    (entry/'manifest.json').write_bytes(json_bytes({'key':'k','files':inventory(entry)}))
    assert verified_cache(entry,'k')[0]=={'outputs':{}}
    (entry/'result.json').write_text('{"outputs":{"model":"evil"}}')
    assert verified_cache(entry,'k')[0] is None


def test_missing_quality_is_never_passed_and_html_is_escaped(tmp_path):
    check={'id':'fit','stage':'ik','metric':'marker_rms_m','comparison':'max','limit':.02,'unit':'m','severity':'error'}
    verdict,checks=evaluate([check],{'ik':{'metrics':{}}})
    assert verdict=='needs_review' and checks[0]['status']=='not_assessed'
    assert evaluate([],{} )[0]=='not_assessed'
    report=write_reports(tmp_path,{'name':'<script>alert(1)</script>','stages':{}},[check],[])
    html=Path(report['html_file']).read_text()
    assert '<script>' not in html and '&lt;script&gt;' in html and 'Content-Security-Policy' in html
