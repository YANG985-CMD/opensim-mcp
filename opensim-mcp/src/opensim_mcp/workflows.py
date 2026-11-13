from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import uuid
import bisect

from .core import InputError,MAX_MODEL,MAX_TRC,Settings,bounded_read,execute,read_motion,trc_info,xml_model
from .session import staged_model
from .progress import report


def finite(value,name,lower=None,upper=None):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise InputError(name+' must be finite numeric.')
    if lower is not None and value<lower or upper is not None and value>upper:raise InputError(name+' is outside supported bounds.')
    return float(value)


def vector(value,name,lower=None,upper=None):
    if not isinstance(value,list) or len(value)!=3:raise InputError(name+' must contain three numbers.')
    return [finite(v,name,lower,upper) for v in value]


def _run(cfg,kind,model_path,parameters,static_path=None):
    source=cfg.input_path(model_path,'.osim');original=bounded_read(source,MAX_MODEL);staged=staged_model(original)
    identifier=kind+'-'+uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix=kind+'-',dir=cfg.temp_root) as temp:
        work=Path(temp);(work/'model.osim').write_bytes(staged)
        request={'kind':kind,'parameters':parameters}
        if static_path:
            path=cfg.input_path(static_path,'.trc');data=bounded_read(path,MAX_TRC);trc_info(data)
            (work/'static.trc').write_bytes(data);request['static_trc']='static.trc'
        (work/'request.json').write_text(json.dumps(request,allow_nan=False),encoding='utf-8')
        native=execute(cfg,['extended','request.json'],work,cfg.timeout,force_api=True)
        result=json.loads(bounded_read(work/'native-result.json',1024*1024))
        outputs=[work/name for name in result.pop('outputs')]
        if not outputs or any(p.parent!=work or not p.is_file() or p.stat().st_size>64*1024*1024 for p in outputs):
            raise InputError('Missing/invalid native output artifacts.')
        for path in outputs:
            if path.suffix=='.osim':xml_model(bounded_read(path,MAX_MODEL))
            if path.suffix in {'.mot','.sto'}:read_motion(path)
        report('validating_outputs')
        destination=cfg.results_root/identifier;destination.mkdir(parents=True)
        try:
            for path in outputs:shutil.copyfile(path,destination/path.name)
            result.update(status='completed',workflow=kind,backend='opensim_api',job_id=identifier,
                          elapsed_seconds=native['elapsed_seconds'],files=[str(destination/p.name) for p in outputs])
            for key,name in (('model_file','scaled.osim'),('solution_file','solution.sto')):
                if (destination/name).is_file():result[key]=str(destination/name)
            safe_parameters={k:v for k,v in parameters.items() if k!='frames'}
            provenance={**result,'parameters':safe_parameters,'model_sha256':hashlib.sha256(original).hexdigest(),
                        'static_sha256':hashlib.sha256(data).hexdigest() if static_path else None}
            (destination/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
            return result
        except BaseException:
            shutil.rmtree(destination,ignore_errors=True);raise


def run_scale(cfg:Settings,model_path:str,subject_mass_kg:float,body_scales:dict[str,list[float]]|None=None,
              static_marker_path:str|None=None,measurements:list[dict]|None=None,
              preserve_mass_distribution:bool=True,max_measurement_error_m:float|None=None) -> dict:
    finite(subject_mass_kg,'subject_mass_kg',.001,10000)
    if type(preserve_mass_distribution) is not bool:raise InputError('preserve_mass_distribution must be boolean.')
    scales=body_scales or {};measures=measurements or []
    if not isinstance(scales,dict) or len(scales)>300 or not isinstance(measures,list) or len(measures)>300:raise InputError('Invalid scaling definitions.')
    for body,factors in scales.items():
        if not isinstance(body,str) or not body or len(body)>200:raise InputError('Invalid body name.')
        vector(factors,'scale factors',.2,5)
    if not scales and not measures:raise InputError('Provide explicit body scales or marker-pair measurements.')
    if bool(static_marker_path)!=bool(measures):raise InputError('Marker measurements and static_marker_path must be supplied together.')
    for item in measures:
        if not isinstance(item,dict) or set(item)!={'body','axes','marker_pairs'}:raise InputError('Measurement needs body, axes and marker_pairs.')
        if not isinstance(item['axes'],list) or not item['axes'] or len(set(item['axes']))!=len(item['axes']) or set(item['axes'])-set('xyz'):
            raise InputError('Measurement axes must select x/y/z without duplicates.')
        pairs=item['marker_pairs']
        if not isinstance(pairs,list) or not 1<=len(pairs)<=100 or any(not isinstance(p,list) or len(p)!=2 or p[0]==p[1] or any(not isinstance(n,str) or not n or len(n)>200 for n in p) for p in pairs):
            raise InputError('Measurement marker_pairs must be pairs of distinct marker names.')
    if max_measurement_error_m is not None:finite(max_measurement_error_m,'max_measurement_error_m',0,1)
    return _run(cfg,'scale',model_path,{'subject_mass_kg':subject_mass_kg,'body_scales':scales,'measurements':measures,
                'preserve_mass_distribution':preserve_mass_distribution,'max_measurement_error_m':max_measurement_error_m},static_marker_path)


def bounds(value,name):
    if not isinstance(value,list) or len(value) not in {1,2}:raise InputError(name+' requires [fixed] or [lower,upper].')
    values=[finite(v,name,-1e9,1e9) for v in value]
    if len(values)==2 and values[0]>values[1]:raise InputError(name+' bounds are reversed.')
    return values


def run_moco(cfg:Settings,model_path:str,initial_time:float,final_time:float,state_bounds:dict[str,dict],
             control_bounds:dict[str,list[float]],control_effort_weight:float=1.0,mesh_intervals:int=20,
             max_iterations:int=500,convergence_tolerance:float=1e-4,constraint_tolerance:float=1e-4,
             refine_mesh:bool=False,max_mesh_objective_relative_change:float=.02) -> dict:
    finite(initial_time,'initial_time',0,1e6);finite(final_time,'final_time',0,1e6)
    if not 0<final_time-initial_time<=100:raise InputError('Moco duration must be in (0,100] seconds.')
    if not isinstance(state_bounds,dict) or not 1<=len(state_bounds)<=500 or not isinstance(control_bounds,dict) or not 1<=len(control_bounds)<=500:
        raise InputError('Provide 1..500 explicit state and control bounds.')
    for path,info in state_bounds.items():
        if not isinstance(path,str) or not path.startswith('/') or len(path)>1000 or not isinstance(info,dict) or set(info)-{'bounds','initial','final'} or 'bounds' not in info:
            raise InputError('Each state needs an absolute path and bounds, with optional initial/final bounds.')
        general=bounds(info['bounds'],path)
        for endpoint in ('initial','final'):
            if endpoint in info:
                values=bounds(info[endpoint],endpoint)
                if any(v<general[0] or v>general[-1] for v in values):raise InputError('Endpoint bounds must lie within state bounds.')
    for path,info in control_bounds.items():
        if not isinstance(path,str) or not path.startswith('/') or len(path)>1000:raise InputError('Control paths must be absolute.')
        bounds(info,path)
    finite(control_effort_weight,'control_effort_weight',1e-12,1e6)
    if type(mesh_intervals) is not int or not 5<=mesh_intervals<=200:raise InputError('mesh_intervals must be 5..200.')
    if type(max_iterations) is not int or not 1<=max_iterations<=2000:raise InputError('max_iterations must be 1..2000.')
    finite(convergence_tolerance,'convergence_tolerance',1e-10,.01)
    finite(constraint_tolerance,'constraint_tolerance',1e-10,.01)
    if type(refine_mesh) is not bool:raise InputError('refine_mesh must be boolean.')
    finite(max_mesh_objective_relative_change,'max_mesh_objective_relative_change',0,1)
    return _run(cfg,'moco',model_path,dict(initial_time=initial_time,final_time=final_time,state_bounds=state_bounds,
                control_bounds=control_bounds,control_effort_weight=control_effort_weight,mesh_intervals=mesh_intervals,
                max_iterations=max_iterations,convergence_tolerance=convergence_tolerance,constraint_tolerance=constraint_tolerance,
                refine_mesh=refine_mesh,max_mesh_objective_relative_change=max_mesh_objective_relative_change))


def run_joint_reaction(cfg:Settings,model_path:str,coordinates_path:str,loads_path:str|None=None,
                       external_forces:list[dict[str,str]]|None=None,no_external_loads:bool=False,
                       start_time:float|None=None,end_time:float|None=None,lowpass_cutoff_hz:float|None=None,
                       joint_names:list[str]|None=None,on_body:str='child',in_frame:str='ground',
                       forces_path:str|None=None,ignore_actuators:bool=False) -> dict:
    from .analysis import run_analysis
    return run_analysis(cfg,'joint_reaction',model_path,coordinates_path,loads_path,external_forces,no_external_loads,
                        start_time,end_time,lowpass_cutoff_hz,joint_names,on_body,in_frame,forces_path,ignore_actuators)


def assess_ik_quality(cfg:Settings,model_path:str,coordinates_path:str,marker_path:str,
                      markers:list[str]|None=None,max_frames:int=200,rms_threshold_m:float|None=None,
                      interpolation:str='none') -> dict:
    motion_path=cfg.input_path(coordinates_path,Path(coordinates_path).suffix.lower())
    if motion_path.suffix.lower() not in {'.mot','.sto'}:raise InputError('Coordinates must be .mot/.sto.')
    motion=read_motion(motion_path)
    if motion['in_degrees'].lower() not in {'yes','no','true','false'}:raise InputError('Coordinate angle units must be explicit.')
    path=cfg.input_path(marker_path,'.trc');raw=bounded_read(path,MAX_TRC);trc=trc_info(raw)
    _,model=xml_model(bounded_read(cfg.input_path(model_path,'.osim'),MAX_MODEL))
    common=sorted({e.get('name') for e in model.iter('Marker')}&set(trc['markers']))
    selected=common if markers is None else markers
    if not isinstance(selected,list) or not selected or len(set(selected))!=len(selected) or set(selected)-set(common):raise InputError('Select unique shared model/TRC markers.')
    if type(max_frames) is not int or not 2<=max_frames<=2000:raise InputError('max_frames must be 2..2000.')
    if rms_threshold_m is not None:finite(rms_threshold_m,'rms_threshold_m',0,1)
    if interpolation not in {'none','linear'}:raise InputError('interpolation must be none or linear.')
    coordinates={e.get('name') for e in model.iter('Coordinate')}
    if not coordinates<=set(motion['columns']):raise InputError('Complete model coordinate columns are required.')
    count=len(motion['rows']);ids=sorted({round(i*(count-1)/(min(count,max_frames)-1)) for i in range(min(count,max_frames))})
    frames=[];needed={};times=trc['times'];maximum_delta=0.;interpolated=0
    time_tolerance=min(min(b-a for a,b in zip(times,times[1:]))*.001,
                       max(1e-6,abs(motion['rows'][-1][0])*1e-6))
    for index in ids:
        row=motion['rows'][index];position=bisect.bisect_left(times,row[0])
        candidates=[j for j in (position-1,position) if 0<=j<len(times)]
        nearest=min(candidates,key=lambda j:abs(times[j]-row[0]))
        delta=abs(times[nearest]-row[0]);maximum_delta=max(maximum_delta,delta)
        sources=[(nearest,1.)]
        if delta>time_tolerance:
            if interpolation!='linear':raise InputError('Motion/TRC grids differ; explicitly request interpolation=linear or supply coincident samples.')
            if not 0<position<len(times):raise InputError('Marker quality interpolation cannot extrapolate.')
            left,right=position-1,position
            if times[right]-times[left]>3/trc['data_rate']:raise InputError('Marker interpolation gap exceeds three declared sample periods.')
            fraction=(row[0]-times[left])/(times[right]-times[left])
            sources=[(left,1-fraction),(right,fraction)];interpolated+=1
        for source,weight in sources:needed.setdefault(source,[]).append((len(frames),weight))
        frames.append({'time':row[0],'coordinates':{n:row[motion['columns'].index(n)] for n in coordinates},
                       'markers':{name:[0.,0.,0.] for name in selected}})
    scale=.001 if trc['units']=='mm' else 1.
    indexes={name:2+3*trc['markers'].index(name) for name in selected}
    rows=(line for line in raw.decode('utf-8-sig').splitlines()[6:] if line.strip())
    for index,line in enumerate(rows):
        if index in needed:
            values=[float(x) for x in line.split()]
            for frame,weight in needed[index]:
                for name,start in indexes.items():
                    for axis in range(3):frames[frame]['markers'][name][axis]+=values[start+axis]*scale*weight
    return _run(cfg,'ik_quality',model_path,{'frames':frames,'markers':selected,'in_degrees':motion['in_degrees'],
                 'rms_threshold_m':rms_threshold_m,'source_coordinate_rows':count,'checked_frames':len(frames),
                 'max_time_match_error_s':maximum_delta,'time_match_tolerance_s':time_tolerance,
                 'interpolation':interpolation,'interpolated_frames':interpolated,
                 'coordinate_sha256':hashlib.sha256(bounded_read(motion_path,64*1024*1024)).hexdigest(),
                 'marker_sha256':hashlib.sha256(raw).hexdigest()})
