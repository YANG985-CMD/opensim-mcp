import copy,json
from pathlib import Path
import pytest
from opensim_mcp.core import InputError,Settings
from opensim_mcp.workbench import alignment,create_workbench,validate_state
from opensim_mcp.visual_signals import inspect_workspace
from test_visual_signals import scene

def entry(times,offset=0):
    data=scene();data['frames']=[dict(copy.deepcopy(data['frames'][0]),time=t) for t in times]
    return dict(scene=data,time_offset_s=offset)

def state():return dict(schema='opensim_view_state_v1',workbench_id='identity',frame=0,camera=dict(yaw=.7,pitch=.25,zoom=2.7),selected=None,hidden=[[]],opacity=1,layers=dict(surfaces=True,muscles=True,markers=False,skeleton=False),curve='coordinate:q',measurement=dict(scene=0,points=[]),note='review')

def test_explicit_offset_and_nearest_pose_match_without_interpolation():
    a=alignment([entry([0,.5,1]),entry([10,10.55,11],-10)],.02)
    assert a['times']==[0,.5,1] and a['indices']==[[0,0],[1,None],[2,2]] and a['coverage']==[3,2]

def test_exact_tie_chooses_earlier_sample():
    assert alignment([entry([0,.5,1]),entry([0,1])],.5)['indices'][1]==[1,0]

@pytest.mark.parametrize('times',[[2,3],[1,2],[.01,.02]])
def test_nonoverlap_or_too_few_primary_samples_rejected(times):
    with pytest.raises(InputError):alignment([entry([0,.5,1]),entry(times)],.01)

@pytest.mark.parametrize('value',[-1,61,float('nan'),True])
def test_time_tolerance_is_finite_and_bounded(value):
    with pytest.raises(InputError):alignment([entry([0,1])],value)

@pytest.mark.parametrize('field,value',[('workbench_id','stale'),('frame',999),('opacity',0),('curve','coordinate:missing'),('note','x'*1001),('selected',{'scene':0,'component':{'kind':'body','name':'missing'}}),('measurement',{'scene':0,'points':[{'kind':'body','name':'/bodyset/link'}]})])
def test_saved_state_rejects_stale_inputs_unknown_ids_and_invalid_values(field,value):
    v=state();v[field]=value
    with pytest.raises(InputError):validate_state(v,[entry([0,1])],'identity',{'times':[0,1]})

def test_view_state_accepts_finite_camera_selection_measurement_and_note():
    v=state();v['selected']=dict(scene=0,component=dict(kind='frame',name='/bodyset/link'));v['measurement']['points']=[dict(kind='marker',name='point')]
    assert validate_state(v,[entry([0,1])],'identity',{'times':[0,1]})==v

def setup(tmp_path,two=True):
    work=tmp_path/'work';work.mkdir();cfg=Settings((tmp_path,),tmp_path/'results',work,None)
    paths=[]
    for i in range(2 if two else 1):
        path=tmp_path/f'scene{i}.json';path.write_text(json.dumps(scene()),encoding='utf-8');paths.append(dict(path=str(path),label=f'View {i}',time_offset_s=0))
    return cfg,paths

def test_workbench_manifest_has_copied_scene_integrity_and_no_input_absolute_paths(tmp_path):
    cfg,paths=setup(tmp_path);result=create_workbench(cfg,paths,0)
    manifest=inspect_workspace(cfg,result['project_file']);assert manifest['verified'] and result['scene_count']==2
    assert set(manifest['assets'])=={'scene-0.json','scene-1.json','viewer.html'}
    assert str(tmp_path) not in Path(result['html_file']).read_text(encoding='utf-8')
    target=Path(result['html_file']).parent/'scene-1.json';target.write_text('{}')
    with pytest.raises(InputError,match='hash mismatch'):inspect_workspace(cfg,result['project_file'])

def test_label_and_note_do_not_escape_script_context(tmp_path):
    cfg,paths=setup(tmp_path,False);paths[0]['label']='</script><script>bad</script>'
    result=create_workbench(cfg,paths,0);html=Path(result['html_file']).read_text(encoding='utf-8')
    assert '</script><script>bad' not in html and '\\u003c/script>' in html

def test_mapping_units_and_uniqueness_are_explicit(tmp_path):
    cfg,paths=setup(tmp_path);mapping=[dict(left=dict(kind='coordinate',name='q'),right=dict(kind='coordinate',name='q'))]
    with pytest.raises(InputError,match='one-to-one'):create_workbench(cfg,paths,0,mapping*2)
    d=scene();d['coordinate_units']['q']='deg';Path(paths[1]['path']).write_text(json.dumps(d))
    with pytest.raises(InputError,match='units'):create_workbench(cfg,paths,0,mapping)

def test_saved_view_can_be_used_for_same_scene_bytes_and_rejects_changed_alignment(tmp_path):
    cfg,paths=setup(tmp_path,False);first=create_workbench(cfg,paths,0);v=state();v.update(workbench_id=first['workbench_id']);v['note']='same input'
    file=tmp_path/'view.json';file.write_text(json.dumps(v))
    assert create_workbench(cfg,paths,0,view_state_path=str(file))['workbench_id']==first['workbench_id']
    with pytest.raises(InputError,match='different'):create_workbench(cfg,paths,.01,view_state_path=str(file))

def test_scene_units_must_be_meters(tmp_path):
    cfg,paths=setup(tmp_path,False);data=scene();data['units']='mm';Path(paths[0]['path']).write_text(json.dumps(data))
    with pytest.raises(InputError,match='meters'):create_workbench(cfg,paths,0)
