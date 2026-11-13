import json,math
from pathlib import Path
import pytest
from opensim_mcp.core import Settings,InputError
from opensim_mcp.muscle_forces import statistics,assess_series,estimate_volumes,digest,load_report
from opensim_mcp.muscle_display import sample_series,bind
from opensim_mcp.native_muscle import fingerprint

LIMITS=dict(max_reserve_peak_fraction=.1,max_residual_actuator_force_N=20.,max_residual_actuator_moment_Nm=75.)
DEF=dict(name='reserve',coordinate='q',role='reserve',unit='N',optimal_force=1.,min_control=-100.,max_control=100.)

def test_force_impulse_mean_and_rms_use_time_weighting_on_irregular_samples():
    r=statistics([0,1,3],[0,2,2]);assert r['integral']==5 and r['mean']==pytest.approx(5/3) and r['rms']==pytest.approx(math.sqrt(10/3))

@pytest.mark.parametrize('reserve,demand,status',[(1,100,'pass'),(20,100,'needs_review'),(0,0,'pass'),(1,0,'needs_review')])
def test_reserve_limits_and_zero_reference_are_not_accepted_by_division(reserve,demand,status):
    q=assess_series([0,1],{'reserve':[reserve]*2},{'m':[.2,.2]},{'q_force':[demand]*2},[DEF],LIMITS)
    assert q['status']==status
    if demand==0 and reserve:assert q['checks'][0]['value'] is None

@pytest.mark.parametrize('activation',[-.01,1.01])
def test_activation_outside_physical_range_is_rejected(activation):
    with pytest.raises(InputError,match='activation'):assess_series([0,1],{'reserve':[0,0]},{'m':[activation]*2},{'q_force':[10,10]},[DEF],LIMITS)

def test_volume_units_and_measurement_provenance(tmp_path,monkeypatch):
    monkeypatch.setattr('opensim_mcp.muscle_forces.metadata',lambda *a:dict(physics_signature='A',muscles={'m':dict(max_isometric_force_N=100,optimal_fiber_length_m=.6)}))
    cfg=Settings((tmp_path,),tmp_path/'results',tmp_path/'scratch',None)
    r=estimate_volumes(cfg,'ignored',300000.)
    assert r['muscles']['m']['volume_cm3']==pytest.approx(200)
    assert r['muscles']['m']['source']=='parameter_estimate'
    with pytest.raises(InputError,match='source'):estimate_volumes(cfg,'ignored',None,{'m':120},'')
    measured=estimate_volumes(cfg,'ignored',None,{'m':120},'User-supplied MRI segmentation')
    assert measured['muscles']['m']['source']=='supplied_measurement'
    with pytest.raises(InputError,match='specific tension'):estimate_volumes(cfg,'ignored')

def report(tmp_path,**changes):
    context=dict(coordinates_sha256='motion',loads_sha256=None,external_forces=[],no_external_loads=True,lowpass_cutoff_hz=None,actuator_profile=[DEF],quality_limits=LIMITS)
    r=dict(schema='opensim_muscle_force_study_v1',label='test',source_model_sha256='model',source_model_physics_signature='A',study_context=context,
           context_sha256=digest(json.dumps(context,sort_keys=True,allow_nan=False).encode()),solver='SO',quality={'status':'pass'},
           series=dict(times=[0,1],forces_N={'m':[10,20]},activations={'m':[.1,.2]}),audit_series=dict(actuator_forces={'reserve':[0,0]},reference_ID={'q_force':[10,10]}))
    r.update(changes);p=tmp_path/'report.json';p.write_text(json.dumps(r),encoding='utf-8');return p,r

def test_report_quality_is_recalculated_instead_of_trusting_saved_pass_label(tmp_path):
    p,r=report(tmp_path);r['audit_series']['actuator_forces']['reserve']=[5,5];p.write_text(json.dumps(r),encoding='utf-8')
    cfg=Settings((tmp_path,),tmp_path/'results',tmp_path/'work',None)
    assert load_report(cfg,str(p))['quality']['status']=='needs_review'
    r['study_context']['loads_sha256']='changed';p.write_text(json.dumps(r),encoding='utf-8')
    with pytest.raises(InputError,match='context hash'):load_report(cfg,str(p))

def test_force_binding_requires_same_physics_motion_and_explicit_interpolation(tmp_path):
    p,r=report(tmp_path);cfg=Settings((tmp_path,),tmp_path/'results',tmp_path/'work',None)
    def scene(signature='A'):return dict(physics_signature=signature,muscle_names=['m'],frames=[dict(time=t) for t in (0,.5,1)])
    with pytest.raises(InputError,match='different coordinate'):bind(cfg,scene(),'other',str(p))
    with pytest.raises(InputError,match='physics'):bind(cfg,scene('B'),'motion',str(p))
    with pytest.raises(InputError,match='interpolation'):bind(cfg,scene(),'motion',str(p))
    d=scene();bind(cfg,d,'motion',str(p),interpolation='linear');assert d['frames'][1]['muscle_forces_N']['m']==15

def test_interpolation_cannot_extrapolate_or_bridge_a_large_gap():
    s=dict(times=[0,1,10],forces_N={'m':[10,20,30]},activations={'m':[.1,.2,.3]})
    with pytest.raises(InputError,match='extrapolate'):sample_series(s,[-.1],['m'],'linear')
    with pytest.raises(InputError,match='gap'):sample_series(s,[5],['m'],'linear')

def test_physics_identity_ignores_appearance_but_detects_mass_changes():
    class Model:
        def __init__(self,mass,color):self.mass=mass;self.color=color
        def dump(self):return f'<Model name="x"><Body><mass>{self.mass}</mass><attached_geometry><Mesh><Appearance><color>{self.color}</color></Appearance></Mesh></attached_geometry></Body></Model>'
    assert fingerprint(Model(1,'red'))==fingerprint(Model(1,'blue'))
    assert fingerprint(Model(1,'red'))!=fingerprint(Model(2,'red'))
