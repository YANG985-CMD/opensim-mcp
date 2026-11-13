import json
from pathlib import Path

import pytest

from opensim_mcp.core import InputError,Settings
from opensim_mcp.visual_signals import attach_signals,bind_sources,inspect_workspace,read_source,sample


def scene():
    return dict(name='Generic model',units='m',physics_signature='physics',coordinate_system='Y up',coordinate_units={'q':'rad'},
        frame_to_body={'/ground':'/ground','/bodyset/link':'/bodyset/link'},meshes=[],muscle_names=['m'],comparison_frames=[],joint_links=[],
        frames=[dict(time=t,transforms={'/ground':[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],'/bodyset/link':[1,0,0,0,0,1,0,0,0,0,1,0,0,1,0,1]},
          markers={'point':[0,1,0]},coordinate_values={'q':t},muscle_paths={'m':[[0,0,0],[0,1,0]]}) for t in (0.,.5,1.)],
        warnings=[],source_rows=3,error_color_range_m=.03,muscle_result_info=[])


def cfg(tmp_path):
    (tmp_path/'work').mkdir(exist_ok=True)
    return Settings((tmp_path,),tmp_path/'results',tmp_path/'work',None)


def spec(tmp_path,rows='0,0\n1,10\n'):
    p=tmp_path/'signals.csv';p.write_text('time_s,value\n'+rows,encoding='utf-8-sig')
    return dict(path=str(p),label='MATLAB',time_column='time_s',time_unit='s',time_offset_s=0.,interpolation='linear',max_gap_s=1.,
                channels=[dict(column='value',label='Signal',unit='rad',component=dict(kind='coordinate',name='q'))])


def test_linear_and_previous_have_distinct_meanings():
    assert sample([0.,1.],[0.,10.],[0.,.5,1.],'linear',1.)[0]==[0.,5.,10.]
    assert sample([0.,1.],[0.,10.],[0.,.5,1.],'previous',1.)[0]==[0.,0.,10.]


@pytest.mark.parametrize('method,gap,target,message', [('none',1.,.5,'explicit'),('linear',.2,.5,'gap'),('previous',.2,.5,'gap'),('linear',1.,1.1,'cover')])
def test_no_implicit_interpolation_gap_filling_or_extrapolation(method,gap,target,message):
    with pytest.raises(InputError,match=message):sample([0.,1.],[1.,2.],[target],method,gap)


def test_ms_and_offset_are_explicit_and_values_are_not_angle_converted(tmp_path):
    source=spec(tmp_path,'100,0\n1100,180\n');source.update(time_unit='ms',time_offset_s=-.1)
    data=scene();bind_sources(cfg(tmp_path),data,[source])
    assert data['external_signals'][0]['times']==pytest.approx([0.,1.])
    assert data['external_signals'][0]['frame_values']==[0.,90.,180.]
    assert data['signal_provenance'][0]['model_identity']=='explicit_component_mapping_only'


@pytest.mark.parametrize('rows,message',[('0,1\n0,2\n','increasing'),('0,NaN\n1,2\n','nonfinite'),('0,hello\n1,2\n','numeric'),('0,1,2\n1,3\n','width')])
def test_invalid_numeric_csv_is_rejected(tmp_path,rows,message):
    with pytest.raises(InputError,match=message):read_source(cfg(tmp_path),spec(tmp_path,rows))


@pytest.mark.parametrize('component',[dict(kind='body',name='/bodyset/missing'),dict(kind='muscle',name='missing'),dict(kind='coordinate',name='other'),dict(kind=[],name='q'),dict(kind='coordinate',name=[])])
def test_explicit_binding_must_exist_in_scene(tmp_path,component):
    source=spec(tmp_path);source['channels'][0]['component']=component
    with pytest.raises(InputError,match='component'):bind_sources(cfg(tmp_path),scene(),[source])


def test_optional_physics_signature_must_match(tmp_path):
    source=spec(tmp_path);source['model_physics_signature']='stale'
    with pytest.raises(InputError,match='physics'):bind_sources(cfg(tmp_path),scene(),[source])


def test_unknown_source_schema_rejected(tmp_path):
    source=spec(tmp_path);source['schema']='unknown_v99'
    with pytest.raises(InputError,match='schema'):read_source(cfg(tmp_path),source)


def test_workspace_copies_sources_hashes_and_rejects_tampering(tmp_path):
    source=spec(tmp_path);data=tmp_path/'animation.json';data.write_text(json.dumps(scene()))
    settings=cfg(tmp_path);result=attach_signals(settings,str(data),[source])
    report=inspect_workspace(settings,result['project_file']);assert report['verified']
    assert set(report['assets'])=={'inputs/signal-0.csv','animation.json','viewer.html'}
    assert report['component_ids']['coordinate']==['q']
    Path(result['html_file']).write_text('tampered')
    with pytest.raises(InputError,match='hash mismatch'):inspect_workspace(settings,result['project_file'])


@pytest.mark.parametrize('name',['../outside.csv','C:/private.txt','inputs\\x.csv'])
def test_workspace_cannot_grant_file_access_outside_itself(tmp_path,name):
    project=tmp_path/'visualization.json';project.write_text(json.dumps(dict(schema='opensim_visualization_project_v1',assets={name:'hash','viewer.html':'hash'})))
    with pytest.raises(InputError,match='path'):inspect_workspace(cfg(tmp_path),str(project))


def test_payload_text_is_escaped_for_offline_html(tmp_path):
    source=spec(tmp_path);source['label']='</script><script>alert(1)</script>'
    data=tmp_path/'animation.json';data.write_text(json.dumps(scene()))
    result=attach_signals(cfg(tmp_path),str(data),[source]);html=Path(result['html_file']).read_text(encoding='utf-8')
    assert '</script><script>alert' not in html
    assert '\\u003c/script>' in html


def test_rebinding_requires_original_scene_and_limits_are_explicit(tmp_path):
    source=spec(tmp_path);data=scene();bind_sources(cfg(tmp_path),data,[source])
    with pytest.raises(InputError,match='already'):bind_sources(cfg(tmp_path),data,[source])
    del source['max_gap_s']
    with pytest.raises(InputError,match='explicit'):read_source(cfg(tmp_path),source)
