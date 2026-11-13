from pathlib import Path
import json
import pytest
from opensim_mcp.core import Settings,InputError
from opensim_mcp.wearable import validate_links,prepare_motion

@pytest.fixture
def context(tmp_path):
    mesh=tmp_path/'part.stl';mesh.write_bytes(b'placeholder - validation never parses')
    cfg=Settings((tmp_path,),tmp_path/'out',tmp_path/'temp',None)
    link=dict(name='cuff',parent_frame='/bodyset/femur_r',mesh_path=str(mesh),mesh_units='mm',mass_kg=.5,mass_center_m=[0.,0.,0.],inertia_kg_m2=[.001,.001,.001,0.,0.,0.],joint_type='WeldJoint')
    return cfg,link

def test_device_mass_and_units_are_explicit(context):
    cfg,link=context;assert validate_links(cfg,[link],True)[0]['unit_scale']==.001
    for field in ('mass_kg','mesh_units','inertia_kg_m2','joint_type'):
        bad=dict(link);del bad[field]
        with pytest.raises(InputError):validate_links(cfg,[bad],True)
    bad=dict(link,mass_kg=float('nan'))
    with pytest.raises(InputError):validate_links(cfg,[bad],True)

def test_no_implicit_topology_contact_or_landmark_resizing(context):
    cfg,link=context
    for changed in (dict(link,joint_type='MagicJoint'),dict(link,contact_stiffness=1000),dict(link,name='../outside'),dict(link,mesh_units='guess')):
        with pytest.raises(InputError):validate_links(cfg,[changed],True)
    fitted=dict(link,landmarks={'cad_points':[[0,0,0],[1,0,0],[0,1,0]],'parent_points_m':[[0,0,0],[1,0,0],[0,1,0]],'allow_uniform_scale':True})
    with pytest.raises(InputError,match='invalidate'):validate_links(cfg,[fitted],True)

def test_visual_only_attachment_cannot_silently_add_mass(context):
    cfg,link=context
    with pytest.raises(InputError):validate_links(cfg,[link],False)
    visual={k:v for k,v in link.items() if k not in {'mass_kg','mass_center_m','inertia_kg_m2','joint_type'}}
    assert 'mass_kg' not in validate_links(cfg,[visual],False)[0]

def test_prepared_motion_cannot_use_changed_model(tmp_path):
    cfg=Settings((tmp_path,),tmp_path/'out',tmp_path/'temp',None);model=tmp_path/'model.osim';model.write_text('changed')
    report=tmp_path/'assembly.json';report.write_text(json.dumps(dict(model_file=str(model),model_sha256='wrong')))
    with pytest.raises(InputError,match='changed'):prepare_motion(cfg,str(report),'unused')
