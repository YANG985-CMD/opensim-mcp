"""Bounded inputs for structured native calibration and actuator workflows."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from .core import InputError, MAX_MODEL, bounded_read, execute, read_motion, trc_info, xml_model
from .projects import digest
from .session import staged_model
from .workflows import finite


def run_native(cfg, kind, model_path, parameters, assets=None):
    source = cfg.input_path(model_path, '.osim'); original = bounded_read(source, MAX_MODEL)
    with tempfile.TemporaryDirectory(prefix=kind+'-', dir=cfg.temp_root) as name:
        work = Path(name); (work/'model.osim').write_bytes(staged_model(original))
        hashes = {'model':digest(original)}
        for filename, path in (assets or {}).items():
            suffix = Path(path).suffix.lower()
            target = cfg.input_path(path, suffix)
            data = bounded_read(target,64*1024**2)
            if suffix == '.trc': trc_info(data)
            elif suffix in {'.mot','.sto'}: read_motion(target)
            else: raise InputError('Unsupported structured data extension.')
            (work/filename).write_bytes(data); hashes[filename] = digest(data)
        (work/'request.json').write_text(json.dumps({'kind':kind,'parameters':parameters},allow_nan=False),encoding='utf-8')
        native = execute(cfg,['extended','request.json'],work,cfg.timeout,force_api=True)
        result = json.loads(bounded_read(work/'native-result.json',2*1024**2)); outputs = result.pop('outputs')
        if not isinstance(outputs,list) or not outputs or len(outputs)>100: raise InputError('Invalid output inventory.')
        for filename in outputs:
            p = work/filename
            if p.parent != work or not p.is_file() or p.is_symlink(): raise InputError('Invalid native output path.')
            raw = bounded_read(p,64*1024**2)
            if p.suffix == '.osim': xml_model(raw)
            if p.suffix in {'.mot','.sto'}:
                # MarkerPlacer emits a valid one-frame static pose; do not treat it as an analysis time series.
                if filename != 'static_pose.mot': read_motion(p)
        destination = cfg.results_root/(kind+'-'+uuid.uuid4().hex); destination.mkdir(parents=True)
        try:
            for filename in outputs: shutil.copyfile(work/filename,destination/filename)
            result.update(status='completed',workflow=kind,files=[str(destination/p) for p in outputs],input_hashes=hashes,
                          elapsed_seconds=native['elapsed_seconds'],parameters=parameters)
            if 'model.osim' in outputs: result['model_file'] = str(destination/'model.osim')
            (destination/'provenance.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
            return result
        except BaseException: shutil.rmtree(destination,ignore_errors=True); raise


def place_markers(cfg, model_path:str, static_marker_path:str, movable_markers:list[str],
                  marker_weights:dict[str,float], coordinate_targets:dict[str,dict]|None=None,
                  start_time:float|None=None, end_time:float|None=None,
                  max_marker_movement_m:float=.02, max_static_motion_m:float=.01):
    if not isinstance(movable_markers,list) or not 1<=len(movable_markers)<=500 or len(set(movable_markers))!=len(movable_markers) or any(not isinstance(n,str) or not n or len(n)>200 for n in movable_markers):
        raise InputError('Provide unique explicitly movable marker names.')
    if not isinstance(marker_weights,dict) or not 1<=len(marker_weights)<=500: raise InputError('Explicit marker weights required.')
    for name,weight in marker_weights.items():
        if not isinstance(name,str) or not name or len(name)>200: raise InputError('Invalid marker name.')
        finite(weight,'marker weight',1e-9,1e9)
    targets=coordinate_targets or {}
    if not isinstance(targets,dict) or len(targets)>500: raise InputError('Invalid coordinate targets.')
    for name,target in targets.items():
        if not isinstance(name,str) or not isinstance(target,dict) or set(target)!={'value','weight'}: raise InputError('Coordinate target requires value and weight in native rad/m units.')
        finite(target['value'],'coordinate target',-1e6,1e6);finite(target['weight'],'coordinate target weight',1e-9,1e9)
    trc=trc_info(bounded_read(cfg.input_path(static_marker_path,'.trc'),64*1024**2))
    start=trc['times'][0] if start_time is None else finite(start_time,'start_time')
    end=trc['times'][-1] if end_time is None else finite(end_time,'end_time')
    if not trc['times'][0]<=start<end<=trc['times'][-1]: raise InputError('Static time interval must be inside TRC with positive duration.')
    finite(max_marker_movement_m,'max_marker_movement_m',1e-9,1.)
    finite(max_static_motion_m,'max_static_motion_m',1e-9,1.)
    return run_native(cfg,'marker_placement',model_path,dict(movable_markers=movable_markers,marker_weights=marker_weights,
        coordinate_targets=targets,start_time=start,end_time=end,max_marker_movement_m=max_marker_movement_m,max_static_motion_m=max_static_motion_m),{'static.trc':static_marker_path})


def actuator_definitions(definitions):
    if not isinstance(definitions,list) or not 1<=len(definitions)<=200: raise InputError('Provide 1..200 explicit actuator definitions.')
    names=set();coordinates=set()
    for d in definitions:
        required={'name','coordinate','role','unit','optimal_force','min_control','max_control'}
        if not isinstance(d,dict) or set(d)!=required: raise InputError('Each actuator requires name, coordinate, role, unit, optimal_force, min_control and max_control.')
        import re
        if not isinstance(d['name'],str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}',d['name']) or d['name'] in names: raise InputError('Actuator names must be unique identifiers.')
        if not isinstance(d['coordinate'],str) or not d['coordinate'] or len(d['coordinate'])>500 or d['coordinate'] in coordinates: raise InputError('Choose one explicit actuator per coordinate.')
        if d['role'] not in {'reserve','residual'} or d['unit'] not in {'N','Nm'}: raise InputError('Explicit reserve/residual role and N/Nm unit required.')
        finite(d['optimal_force'],'optimal_force',1e-9,1e9)
        finite(d['min_control'],'min_control',-1e6,1e6);finite(d['max_control'],'max_control',-1e6,1e6)
        if not d['min_control']<d['max_control']: raise InputError('Control bounds must be ordered.')
        names.add(d['name']);coordinates.add(d['coordinate'])
    return definitions


def configure_actuators(cfg, model_path:str, definitions:list[dict]):
    return run_native(cfg,'configure_actuators',model_path,{'definitions':actuator_definitions(definitions)})


def assess_actuator_usage(cfg, model_path:str, forces_path:str, definitions:list[dict], reference_path:str|None=None):
    """Definitions include explicit force_column and optional reference_column; quantities must share N/Nm units."""
    if not isinstance(definitions,list) or not 1<=len(definitions)<=200: raise InputError('Provide 1..200 assessment definitions.')
    names=set()
    for d in definitions:
        if not isinstance(d,dict) or set(d)-{'name','role','unit','force_column','reference_column'} or not {'name','role','unit','force_column'}<=set(d): raise InputError('Usage definition needs name, role, unit, force_column and optional reference_column.')
        if any(not isinstance(v,str) or not v or len(v)>500 for v in d.values()) or d['name'] in names: raise InputError('Invalid/duplicate usage definition.')
        if d['role'] not in {'reserve','residual'} or d['unit'] not in {'N','Nm'}: raise InputError('Unknown role/unit.')
        if bool(reference_path)!=bool(d.get('reference_column')): raise InputError('Every definition requires a reference column when a reference table is supplied.')
        names.add(d['name'])
    assets={'forces.sto':forces_path}
    if reference_path: assets['reference.sto']=reference_path
    return run_native(cfg,'actuator_usage',model_path,dict(definitions=definitions,has_reference=bool(reference_path)),assets)
