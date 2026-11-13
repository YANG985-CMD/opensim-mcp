"""Explicit C3D conversion; numerical/native imports stay in an isolated worker."""
from __future__ import annotations
import json,math,os,re,shutil,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from .core import InputError,bounded_read,read_motion,trc_info,xml_model,MAX_MODEL
from .process_tree import ProcessTree
from .projects import digest

def rotation_matrix(matrix):
    if not isinstance(matrix,list) or len(matrix)!=3 or any(not isinstance(row,list) or len(row)!=3 for row in matrix):raise InputError('Explicit 3x3 source-to-OpenSim rotation required.')
    if any(type(x) not in {int,float} or not math.isfinite(x) for row in matrix for x in row):raise InputError('Rotation must be finite.')
    if any(abs(sum(matrix[i][k]*matrix[j][k] for k in range(3))-(1 if i==j else 0))>1e-8 for i in range(3) for j in range(3)):raise InputError('Rotation must be orthonormal.')
    a,b,c=matrix;det=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
    if abs(det-1)>1e-8:raise InputError('Rotation must be right-handed (determinant +1).')

def isolated_c3d(cfg,path,operation,parameters):
    source=cfg.input_path(path,'.c3d');data=bounded_read(source,64*1024**2)
    if len(data)<512 or data[1]!=80:raise InputError('Not a supported C3D header.')
    with tempfile.TemporaryDirectory(prefix='c3d-',dir=cfg.temp_root) as name:
        work=Path(name);(work/'input.c3d').write_bytes(data);(work/'request.json').write_text(json.dumps(dict(operation=operation,parameters=parameters)),encoding='utf-8')
        tree=ProcessTree();process=None
        try:
            with (work/'worker.log').open('wb') as log:
                process=tree.spawn([sys.executable,'-B','-m','opensim_mcp.c3d_worker',str(work)],cwd=work,
                    env=dict(os.environ,TEMP=str(work),TMP=str(work),PYTHONDONTWRITEBYTECODE='1'),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000)
                deadline=time.monotonic()+min(cfg.timeout,120)
                while process.poll() is None:
                    if time.monotonic()>deadline:raise TimeoutError('C3D processing exceeded its runtime limit.')
                    if (work/'worker.log').stat().st_size>2*1024**2:raise InputError('C3D worker log limit exceeded.')
                    time.sleep(.04)
                if process.returncode:raise InputError('C3D processing failed: '+bounded_read(work/'worker.log',2*1024**2).decode('utf-8',errors='replace')[-5000:])
            result=json.loads(bounded_read(work/'result.json',2*1024**2));outputs=result.pop('outputs',[])
            result['source_sha256']=digest(data)
            if not outputs:return result
            if len(outputs)>4:raise InputError('Invalid C3D output inventory.')
            for filename in outputs:
                p=work/filename
                if p.parent!=work or p.is_symlink() or not p.is_file():raise InputError('Unsafe C3D output.')
                raw=bounded_read(p,64*1024**2)
                if p.suffix=='.trc':trc_info(raw)
                elif p.suffix=='.mot':read_motion(p)
                elif p.suffix!='.json':raise InputError('Unexpected C3D output type.')
            folder=cfg.results_root/('trial-'+uuid.uuid4().hex);folder.mkdir(parents=True)
            for filename in outputs:shutil.copyfile(work/filename,folder/filename)
            result.update(directory=str(folder),files=[str(folder/n) for n in outputs],marker_path=str(folder/'markers.trc'),loads_path=str(folder/'loads.mot') if 'loads.mot' in outputs else None)
            (folder/'provenance.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8');return result
        finally:
            if process and process.poll() is None:tree.terminate();process.wait(timeout=10)
            tree.close()

def inspect_c3d(cfg,c3d_path):return isolated_c3d(cfg,c3d_path,'inspect',{})

def import_c3d(cfg,c3d_path,source_to_opensim_rotation,plate_mappings=None,force_sign=None,source_up_axis='Z',contact_threshold_N=20.,time_origin='zero',marker_names=None,marker_name_map=None):
    rotation_matrix(source_to_opensim_rotation)
    if source_up_axis not in {'X','Y','Z'} or time_origin not in {'zero','acquisition'}:raise InputError('Invalid source up axis or time origin.')
    if type(contact_threshold_N) not in {int,float} or not math.isfinite(contact_threshold_N) or not 0<contact_threshold_N<=10000:raise InputError('Contact threshold must be (0,10000] N.')
    mappings=plate_mappings or [];names=set();plates=set()
    if not isinstance(mappings,list) or len(mappings)>16:raise InputError('Provide at most 16 explicit plate/body mappings.')
    for p in mappings:
        if not isinstance(p,dict) or set(p)!={'plate_index','body','name'} or type(p['plate_index']) is not int or p['plate_index']<0:raise InputError('Plate mapping needs zero-based plate_index, body and name.')
        if any(not isinstance(p[k],str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,99}',p[k]) for k in ('name','body')) or p['name'] in names or p['plate_index'] in plates:raise InputError('Invalid/duplicate plate identity.')
        names.add(p['name']);plates.add(p['plate_index'])
    if mappings and (type(force_sign) not in {int,float} or force_sign not in {-1,1}):raise InputError('Explicit force_sign=+1 or -1 required; contact forces are not guessed.')
    if mappings and source_up_axis!='Z':raise InputError('The ezc3d force-platform filter assumes source Z-up. Non-Z-up plates require independent calibration/conversion.')
    if marker_names is not None and (not isinstance(marker_names,list) or not 1<=len(marker_names)<=500 or len(set(marker_names))!=len(marker_names) or any(not isinstance(n,str) for n in marker_names)):raise InputError('Invalid marker selection.')
    mapping=marker_name_map or {}
    if not isinstance(mapping,dict) or len(mapping)>500 or any(not isinstance(k,str) or not isinstance(v,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,99}',v) for k,v in mapping.items()):raise InputError('Invalid marker name map.')
    return isolated_c3d(cfg,c3d_path,'import',dict(rotation=source_to_opensim_rotation,plate_mappings=mappings,force_sign=force_sign,
        source_up_axis=source_up_axis,contact_threshold_N=contact_threshold_N,time_origin=time_origin,marker_names=marker_names,marker_name_map=mapping))

def validate_trial(cfg,model_path,marker_path,coordinates_path=None,loads_path=None,external_forces=None,force_units=None):
    from .analysis import table_input,validate_loads
    _,model=xml_model(bounded_read(cfg.input_path(model_path,'.osim'),MAX_MODEL));trc=trc_info(bounded_read(cfg.input_path(marker_path,'.trc'),64*1024**2))
    checks=[];windows=[(trc['times'][0],trc['times'][-1])]
    model_markers={e.get('name') for e in model.iter('Marker')};available=set(trc['markers'])
    missing=sorted(model_markers-available);checks.append(dict(name='model_marker_coverage',status='error' if missing else 'pass',missing=missing))
    checks.append(dict(name='marker_units',status='pass',unit=trc['units']))
    if coordinates_path:
        _,_,table=table_input(cfg,coordinates_path);coordinates={e.get('name') for e in model.iter('Coordinate')}
        missing=sorted(coordinates-set(table['columns']));checks.append(dict(name='coordinate_coverage',status='error' if missing else 'pass',missing=missing))
        checks.append(dict(name='coordinate_units',status='pass' if table['in_degrees'].lower() in {'yes','no','true','false'} else 'error'))
        windows.append((table['rows'][0][0],table['rows'][-1][0]))
    if loads_path:
        _,_,loads=table_input(cfg,loads_path);forces=validate_loads(model,loads,external_forces)
        checks.append(dict(name='external_force_bodies_and_columns',status='pass',count=len(forces)))
        checks.append(dict(name='external_force_units',status='pass' if force_units=={'force':'N','point':'m','torque':'Nm'} else 'error',declared=force_units))
        windows.append((loads['rows'][0][0],loads['rows'][-1][0]))
    elif external_forces:raise InputError('External-force definitions require a loads table.')
    overlap=[max(w[0] for w in windows),min(w[1] for w in windows)]
    checks.append(dict(name='time_overlap',status='pass' if overlap[0]<overlap[1] else 'error',window_s=overlap))
    return dict(valid=not any(c['status']=='error' for c in checks),checks=checks,usable_time_window_s=overlap,
        scope='Structural/data/unit checks only. Axis orientation, force convention and anatomical validity require reviewed acquisition metadata.')
