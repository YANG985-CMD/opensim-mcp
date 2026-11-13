from pathlib import Path
import pytest
from opensim_mcp.core import Settings,InputError,read_motion,trc_info
from opensim_mcp.c3d import import_c3d,inspect_c3d,rotation_matrix,validate_trial
ROOT=Path(__file__).resolve().parents[1]/'examples'

@pytest.fixture
def cfg(tmp_path):
    (tmp_path/'scratch').mkdir();return Settings((ROOT,),tmp_path/'results',tmp_path/'scratch',None,30)

@pytest.mark.parametrize('rotation',[[[1,0,0],[0,1,0],[0,0,-1]],[[1,0,0],[0,2,0],[0,0,1]],[[1,0],[0,1]],[[float('nan'),0,0],[0,1,0],[0,0,1]]])
def test_rotation_rejects_reflection_scale_and_invalid_values(rotation):
    with pytest.raises(InputError):rotation_matrix(rotation)

def test_marker_c3d_native_unit_conversion_and_trial_coverage(cfg):
    inspected=inspect_c3d(cfg,str(ROOT/'slider.c3d'));assert inspected['point_unit']=='mm' and inspected['frames']==11
    result=import_c3d(cfg,str(ROOT/'slider.c3d'),[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    rows=Path(result['marker_path']).read_text(encoding='utf-8').splitlines()
    assert abs(float(rows[-1].split()[2])-.1)<1e-9 and trc_info(Path(result['marker_path']).read_bytes())['units']=='m'
    assert validate_trial(cfg,str(ROOT/'slider.osim'),result['marker_path'])['valid']

def test_force_plate_requires_explicit_sign_and_z_up(cfg):
    p=[dict(plate_index=0,name='right',body='block')];r=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
    with pytest.raises(InputError,match='force_sign'):import_c3d(cfg,str(ROOT/'slider_forceplate.c3d'),r,p)
    with pytest.raises(InputError,match='Z-up'):import_c3d(cfg,str(ROOT/'slider_forceplate.c3d'),r,p,-1,source_up_axis='Y')

def test_native_force_plate_cop_free_moment_and_rotation(cfg):
    r=[[1.,0.,0.],[0.,0.,1.],[0.,-1.,0.]]
    result=import_c3d(cfg,str(ROOT/'slider_forceplate.c3d'),r,[dict(plate_index=0,name='right',body='block')],-1)
    table=read_motion(Path(result['loads_path']));assert len(table['rows'])==110
    values=table['rows'][0];assert abs(values[table['columns'].index('right_force_vy')]-100.)<1e-8
    assert max(abs(values[table['columns'].index('right_torque_'+a)]) for a in 'xyz')<1e-8
    assert result['external_forces'][0]['applied_to_body']=='block'
    assert result['plate_contacts'][0]['contact_fraction']==1.
