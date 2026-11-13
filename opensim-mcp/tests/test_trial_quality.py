import json
from pathlib import Path
import pytest
from opensim_mcp.core import Settings,InputError
from opensim_mcp.trial_quality import gait_cycles,assess_mesh,resample_coordinates

def test_force_cycles_do_not_invent_initial_heel_strike(tmp_path):
    cfg=Settings((tmp_path,),tmp_path/'out',tmp_path/'temp',None);path=tmp_path/'forces.mot'
    values=[100,100,0,0,100,100,100,0,0,100,100]
    path.write_text('test\nversion=1\nnRows=11\nnColumns=2\ninDegrees=no\nendheader\ntime\tup\n'+'\n'.join(f'{i/10}\t{v}' for i,v in enumerate(values)))
    result=gait_cycles(cfg,str(path),'up')
    assert result['initial_contact_onset_unknown']
    assert result['cycles']==[dict(start_time=.4,end_time=.9,duration_s=.5,stance_duration_s=.7-.4)]
    with pytest.raises(InputError):gait_cycles(cfg,str(path),'wrong')
    with pytest.raises(InputError):gait_cycles(cfg,str(path),'up',10,20)

def test_mesh_assessment_requires_all_columns_and_reports_failures(tmp_path):
    cfg=Settings((tmp_path,),tmp_path/'out',tmp_path/'temp',None);path=tmp_path/'study.json'
    path.write_text(json.dumps(dict(comparisons=[dict(states={'q':{'rms':.01},'activation':{'rms':.2}},controls={'u':{'rms':.01}},objective_pass=True,coarse_interval_s=.04,fine_interval_s=.02)])))
    with pytest.raises(InputError,match='every'):assess_mesh(cfg,str(path),{'q':.02},{'u':.02})
    result=assess_mesh(cfg,str(path),{'q':.02,'activation':.1},{'u':.02})
    assert result['status']=='needs_review' and result['comparisons'][0]['failed_columns'][0]['column']=='activation'
    assert assess_mesh(cfg,str(path),{'q':.02,'activation':.3},{'u':.02})['status']=='configured_checks_passed'

def test_resampling_is_explicit_uniform_and_without_extrapolation(tmp_path):
    from opensim_mcp.core import read_motion
    cfg=Settings((tmp_path,),tmp_path/'out',tmp_path/'temp',None);path=tmp_path/'coordinates.mot'
    path.write_text('test\nnRows=3\nnColumns=2\ninDegrees=yes\nendheader\ntime q\n0 0\n.49 49\n1 100\n')
    result=resample_coordinates(cfg,str(path),4.);table=read_motion(Path(result['motion_file']))
    assert result['output_rows']==5 and table['rows'][2]==[.5,50.] and table['in_degrees']=='yes'
    with pytest.raises(InputError,match='extrapolation'):resample_coordinates(cfg,str(path),4.,-.1,1.)
