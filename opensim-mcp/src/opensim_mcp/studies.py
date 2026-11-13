"""Bounded native Moco convergence and model-parameter sensitivity experiments."""
from copy import deepcopy
import bisect,json,math
from pathlib import Path
import uuid
from .core import InputError,read_motion
from .tracking import moco_track,moco_inverse,solver_options
from .structured import run_native
from .transactions import validate_edits
from .progress import report

PROFILES={'moco_track':moco_track,'moco_inverse':moco_inverse}

def base_parameters(profile,parameters):
    if profile not in PROFILES or not isinstance(parameters,dict):raise InputError('Choose moco_track/moco_inverse with structured parameters.')
    import inspect
    try:inspect.signature(PROFILES[profile]).bind(None,**parameters)
    except TypeError as exc:raise InputError(str(exc)) from exc
    return deepcopy(parameters)

def result_file(result,name):
    matches=[Path(f) for f in result['files'] if Path(f).name==name]
    if len(matches)!=1:raise InputError('Expected one '+name)
    return matches[0]

def interpolate(table,t):
    times=[row[0] for row in table['rows']]
    if t<times[0]-1e-9 or t>times[-1]+1e-9:raise InputError('Cannot extrapolate study trajectories.')
    i=max(0,min(len(times)-2,bisect.bisect_right(times,t)-1));a,b=table['rows'][i:i+2];w=(t-a[0])/(b[0]-a[0])
    return [a[k]+w*(b[k]-a[k]) for k in range(len(a))]

def trajectory_difference(first,second):
    if set(first['columns'])!=set(second['columns']):raise InputError('Study state/control identities differ.')
    samples=sorted(set(row[0] for row in first['rows'])|set(row[0] for row in second['rows']))
    start=max(first['rows'][0][0],second['rows'][0][0]);end=min(first['rows'][-1][0],second['rows'][-1][0]);samples=[t for t in samples if start<=t<=end]
    if len(samples)<2:raise InputError('Study trajectories have no common interval.')
    differences={c:[] for c in first['columns'] if c!='time'}
    for t in samples:
        a,b=interpolate(first,t),interpolate(second,t)
        for c in differences:differences[c].append(a[first['columns'].index(c)]-b[second['columns'].index(c)])
    return {c:{'rms':math.sqrt(sum(v*v for v in d)/len(d)),'max_abs':max(abs(v) for v in d),'unit':'native trajectory column units'} for c,d in differences.items()}

def limits(value,name):
    value=value or {}
    if not isinstance(value,dict) or len(value)>1000 or any(not isinstance(k,str) or type(v) not in {float,int} or not math.isfinite(v) or v<0 for k,v in value.items()):raise InputError('Invalid '+name)
    return value

def run_convergence(cfg,profile,parameters,mesh_interval_values_s,state_rms_limits=None,control_rms_limits=None,
                    objective_relative_tolerance=.02,objective_absolute_tolerance=1e-8):
    base=base_parameters(profile,parameters)
    if not isinstance(mesh_interval_values_s,list) or not 2<=len(mesh_interval_values_s)<=4 or any(type(x) not in {int,float} or not math.isfinite(x) or x<=0 for x in mesh_interval_values_s):raise InputError('Provide 2..4 finite positive mesh intervals in seconds.')
    if any(a<=b for a,b in zip(mesh_interval_values_s,mesh_interval_values_s[1:])):raise InputError('Mesh intervals must strictly decrease for refinement.')
    for mesh in mesh_interval_values_s:solver_options(mesh,base.get('max_iterations',500),base.get('convergence_tolerance',1e-4),base.get('constraint_tolerance',1e-4),base['initial_time'],base['final_time'])
    for v in (objective_relative_tolerance,objective_absolute_tolerance):
        if type(v) not in {int,float} or not math.isfinite(v) or v<0:raise InputError('Objective tolerances must be finite and nonnegative.')
    sl,cl=limits(state_rms_limits,'state RMS limits'),limits(control_rms_limits,'control RMS limits');runs=[];comparisons=[]
    for i,mesh in enumerate(mesh_interval_values_s):
        report('mesh_study',case_index=i+1,case_count=len(mesh_interval_values_s));p=dict(base,mesh_interval=mesh);result=PROFILES[profile](cfg,**p)
        runs.append({'mesh_interval_s':mesh,'result':result})
        if i:
            before=runs[i-1]['result'];a=before['quality']['objective'];b=result['quality']['objective'];absolute=abs(b-a);den=max(abs(a),abs(b));relative=absolute/den if den>objective_absolute_tolerance else None
            states=trajectory_difference(read_motion(result_file(before,'states.sto')),read_motion(result_file(result,'states.sto')))
            controls=trajectory_difference(read_motion(result_file(before,'controls.sto')),read_motion(result_file(result,'controls.sto')))
            if set(sl)-set(states) or set(cl)-set(controls):raise InputError('Unknown state/control convergence threshold column.')
            objective_pass=absolute<=objective_absolute_tolerance or (relative is not None and relative<=objective_relative_tolerance)
            selected_pass=all(states[k]['rms']<=v for k,v in sl.items()) and all(controls[k]['rms']<=v for k,v in cl.items())
            all_columns=bool(sl) and bool(cl) and set(sl)==set(states) and set(cl)==set(controls)
            comparisons.append(dict(coarse_interval_s=mesh_interval_values_s[i-1],fine_interval_s=mesh,objective_absolute_change=absolute,objective_relative_change=relative,
                states=states,controls=controls,objective_pass=objective_pass,selected_trajectory_checks_pass=selected_pass,
                all_state_and_control_columns_assessed=all_columns,configured_checks_pass=objective_pass and selected_pass,
                status='configured_checks_passed' if objective_pass and selected_pass and (sl or cl) else 'objective_only' if objective_pass and not(sl or cl) else 'needs_review'))
    folder=cfg.results_root/('mesh-study-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    result=dict(profile=profile,runs=runs,comparisons=comparisons,state_rms_limits=sl,control_rms_limits=cl,
        objective_relative_tolerance=objective_relative_tolerance,objective_absolute_tolerance=objective_absolute_tolerance,
        status=comparisons[-1]['status'],scope='Successive native mesh comparisons on shared trajectory times. Caller thresholds are not physiological validation or a mathematical convergence proof.')
    path=folder/'mesh_study.json';path.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8');result['report_file']=str(path)
    result['files']=[str(path)]+[f for r in runs for f in r['result']['files']];return result

def run_sensitivity(cfg,profile,parameters,variations):
    base=base_parameters(profile,parameters)
    if not isinstance(variations,list) or not 1<=len(variations)<=5:raise InputError('Provide 1..5 explicit parameter variations.')
    labels=set()
    for v in variations:
        if not isinstance(v,dict) or set(v)-{'label','model_edits','parameter_overrides'} or not isinstance(v.get('label'),str) or not 1<=len(v['label'])<=100 or v['label'] in labels:raise InputError('Invalid/duplicate variation label.')
        labels.add(v['label']);edits=v.get('model_edits',[]);overrides=v.get('parameter_overrides',{})
        if edits:validate_edits(edits,0)
        allowed={'tracking_weight','control_effort_weight','ignore_tendon_compliance','minimize_sum_squared_activations'}
        if not isinstance(overrides,dict) or set(overrides)-allowed or not(edits or overrides):raise InputError('Variations require explicit supported physical edits or goal/muscle-option changes.')
        base_parameters(profile,dict(base,**overrides))
    baseline=PROFILES[profile](cfg,**base);cases=[]
    for i,v in enumerate(variations):
        report('sensitivity_study',case_index=i+1,case_count=len(variations));p=dict(base,**v.get('parameter_overrides',{}))
        if v.get('model_edits'):
            changed=run_native(cfg,'study_edit',base['model_path'],dict(edits=v['model_edits']));p['model_path']=changed['model_file']
        result=PROFILES[profile](cfg,**p);a=baseline['quality']['objective'];b=result['quality']['objective']
        cases.append(dict(label=v['label'],variation=v,result=result,objective_change=b-a,objective_relative_change=(b-a)/abs(a) if abs(a)>1e-12 else None,
            state_difference=trajectory_difference(read_motion(result_file(baseline,'states.sto')),read_motion(result_file(result,'states.sto')))))
    folder=cfg.results_root/('sensitivity-'+uuid.uuid4().hex);folder.mkdir(parents=True);path=folder/'sensitivity.json'
    result=dict(profile=profile,baseline=baseline,cases=cases,status='completed',scope='Explicit finite perturbations. Not statistical uncertainty, population validation or a causal clinical claim.')
    path.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8');result['report_file']=str(path);result['files']=[str(path)]+baseline['files']+[f for c in cases for f in c['result']['files']];return result
