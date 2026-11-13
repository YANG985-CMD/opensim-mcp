"""Structured reference-driven Moco profiles. No user setup XML or arbitrary operators."""
from pathlib import Path
from .analysis import table_input, validate_loads
from .core import InputError, MAX_MODEL, bounded_read, xml_model
from .structured import run_native
from .workflows import bounds, finite


def reference_inputs(cfg,model_path,coordinates_path,initial_time,final_time,loads_path,external_forces,no_external_loads):
    if type(no_external_loads) is not bool: raise InputError('no_external_loads must be boolean.')
    _,model=xml_model(bounded_read(cfg.input_path(model_path,'.osim'),MAX_MODEL))
    _,_,table=table_input(cfg,coordinates_path)
    names={e.get('name') for e in model.iter('Coordinate')}
    if not names or not names<=set(table['columns']):raise InputError('Reference must explicitly include all model coordinates by short name.')
    if table['in_degrees'].lower() not in {'yes','no','true','false'}:raise InputError('Reference requires explicit inDegrees.')
    finite(initial_time,'initial_time',0,1e6);finite(final_time,'final_time',0,1e6)
    if not table['rows'][0][0]<=initial_time<final_time<=table['rows'][-1][0] or final_time-initial_time>100:raise InputError('Reference window must be covered and <=100 seconds.')
    if len([r for r in table['rows'] if initial_time<=r[0]<=final_time])<6:raise InputError('At least six reference samples in requested window required.')
    assets={'reference.mot':coordinates_path};forces=[]
    if loads_path:
        if no_external_loads:raise InputError('Cannot supply loads and no_external_loads together.')
        _,_,loads=table_input(cfg,loads_path);forces=validate_loads(model,loads,external_forces)
        if loads['rows'][0][0]>initial_time or loads['rows'][-1][0]<final_time:raise InputError('External loads do not cover Moco window.')
        assets['loads.sto']=loads_path
    elif not no_external_loads or external_forces:raise InputError('Provide explicit external loads or no_external_loads=true.')
    return assets,forces


def solver_options(mesh_interval,max_iterations,convergence_tolerance,constraint_tolerance,initial_time,final_time):
    finite(mesh_interval,'mesh_interval',1e-4,10.)
    if not 5<=(final_time-initial_time)/mesh_interval<=200:raise InputError('Mesh interval must produce 5..200 intervals.')
    if type(max_iterations) is not int or not 1<=max_iterations<=2000:raise InputError('max_iterations must be 1..2000.')
    finite(convergence_tolerance,'convergence_tolerance',1e-10,.01);finite(constraint_tolerance,'constraint_tolerance',1e-10,.01)


def moco_track(cfg,model_path:str,coordinates_path:str,initial_time:float,final_time:float,
               state_bounds:dict,control_bounds:dict,loads_path:str|None=None,external_forces:list[dict]|None=None,
               no_external_loads:bool=False,tracking_weight:float=1.,control_effort_weight:float=.001,
               track_reference_derivatives:bool=True,mesh_interval:float=.05,max_iterations:int=500,
               convergence_tolerance:float=1e-4,constraint_tolerance:float=1e-4,
               max_tracking_rms:dict[str,float]|None=None):
    assets,forces=reference_inputs(cfg,model_path,coordinates_path,initial_time,final_time,loads_path,external_forces,no_external_loads)
    solver_options(mesh_interval,max_iterations,convergence_tolerance,constraint_tolerance,initial_time,final_time)
    if not isinstance(state_bounds,dict) or not 1<=len(state_bounds)<=500 or not isinstance(control_bounds,dict) or not 1<=len(control_bounds)<=500:raise InputError('Complete explicit state/control bounds required.')
    for name,info in state_bounds.items():
        if not isinstance(name,str) or not name.startswith('/') or not isinstance(info,dict) or 'bounds' not in info or set(info)-{'bounds','initial','final'}:raise InputError('Invalid state bounds.')
        general=bounds(info['bounds'],name)
        for endpoint in ('initial','final'):
            if endpoint in info and any(v<general[0] or v>general[-1] for v in bounds(info[endpoint],endpoint)):raise InputError('Endpoint outside state bounds.')
    for name,info in control_bounds.items():
        if not isinstance(name,str) or not name.startswith('/'):raise InputError('Absolute control paths required.')
        bounds(info,name)
    finite(tracking_weight,'tracking_weight',1e-9,1e9);finite(control_effort_weight,'control_effort_weight',0,1e6)
    if type(track_reference_derivatives) is not bool:raise InputError('track_reference_derivatives must be boolean.')
    limits=max_tracking_rms or {}
    if not isinstance(limits,dict) or len(limits)>500:raise InputError('Invalid tracking limits.')
    for name,limit in limits.items():
        if not isinstance(name,str):raise InputError('Invalid coordinate tracking limit.')
        finite(limit,'tracking RMS limit',0,1e6)
    return run_native(cfg,'moco_track',model_path,dict(initial_time=initial_time,final_time=final_time,state_bounds=state_bounds,
        control_bounds=control_bounds,external_forces=forces,no_external_loads=no_external_loads,tracking_weight=tracking_weight,
        control_effort_weight=control_effort_weight,track_reference_derivatives=track_reference_derivatives,mesh_interval=mesh_interval,
        max_iterations=max_iterations,convergence_tolerance=convergence_tolerance,constraint_tolerance=constraint_tolerance,
        max_tracking_rms=limits),assets)


def moco_inverse(cfg,model_path:str,coordinates_path:str,initial_time:float,final_time:float,
                 loads_path:str|None=None,external_forces:list[dict]|None=None,no_external_loads:bool=False,
                 ignore_tendon_compliance:bool=False,minimize_sum_squared_activations:bool=False,
                 mesh_interval:float=.05,max_iterations:int=500,convergence_tolerance:float=1e-4,constraint_tolerance:float=1e-4):
    assets,forces=reference_inputs(cfg,model_path,coordinates_path,initial_time,final_time,loads_path,external_forces,no_external_loads)
    solver_options(mesh_interval,max_iterations,convergence_tolerance,constraint_tolerance,initial_time,final_time)
    if type(ignore_tendon_compliance) is not bool or type(minimize_sum_squared_activations) is not bool:raise InputError('Muscle options must be boolean.')
    return run_native(cfg,'moco_inverse',model_path,dict(initial_time=initial_time,final_time=final_time,
        external_forces=forces,no_external_loads=no_external_loads,ignore_tendon_compliance=ignore_tendon_compliance,
        minimize_sum_squared_activations=minimize_sum_squared_activations,mesh_interval=mesh_interval,max_iterations=max_iterations,
        convergence_tolerance=convergence_tolerance,constraint_tolerance=constraint_tolerance),assets)
