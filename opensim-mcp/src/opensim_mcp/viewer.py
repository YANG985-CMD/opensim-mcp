"""Offline surface-mesh animation from native OpenSim transforms and approved assets."""
from __future__ import annotations
import bisect,json,math,os,posixpath,secrets,shutil,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from defusedxml.ElementTree import fromstring
from .core import InputError,MAX_MODEL,bounded_read,is_under,local_path,read_motion,trc_info,xml_model
from .process_tree import ProcessTree
from .structured import run_native
from .projects import digest

def geometry(cfg,model_path,geometry_roots,mesh_scale_factor):
    source=cfg.input_path(model_path,'.osim');_,model=xml_model(bounded_read(source,MAX_MODEL));records=[];warnings=[]
    roots=[source.parent,source.parent/'Geometry']
    for value in geometry_roots or []:
        path=local_path(value)
        if not path.is_dir() or not any(is_under(path,r) for r in (*cfg.allowed_roots,cfg.results_root)):raise InputError('Geometry roots must already be allowed local directories.')
        roots.append(path)
    def numbers(text,default):
        values=[float(x) for x in text.split()] if text else default
        if len(values)!=len(default) or any(not math.isfinite(v) for v in values):raise InputError('Invalid visual geometry vector.')
        return values
    def walk(node,current=''):
        if node.tag=='Ground':current='/ground'
        elif node.tag=='Body':current='/bodyset/'+node.get('name','')
        elif node.tag.endswith('Joint'):current='/jointset/'+node.get('name','')
        elif node.tag=='PhysicalOffsetFrame':current=current+'/'+node.get('name','')
        attached=node.find('attached_geometry')
        if attached is not None:
            for element in attached:
                if element.tag not in {'Mesh','Brick','Sphere','Ellipsoid'}:
                    warnings.append('Unsupported visual geometry: '+element.tag);continue
                name=element.get('name','visual');own=current+'/'+name;socket=element.findtext('socket_frame','..').strip() or '..'
                frame=posixpath.normpath(socket if socket.startswith('/') else posixpath.join(own,socket))
                record=dict(name=name,frame=frame,type=element.tag.lower(),color=numbers(element.findtext('Appearance/color'),[.45,.6,.7]),scale=numbers(element.findtext('scale_factors'),[1.,1.,1.]))
                if element.tag=='Mesh':
                    filename=element.findtext('mesh_file','').strip();chosen=None
                    for base in roots:
                        path=local_path(base/filename) if not Path(filename).is_absolute() else local_path(filename)
                        if path.suffix.lower() in {'.obj','.stl','.vtp'} and any(is_under(path,r) for r in (*cfg.allowed_roots,cfg.results_root)) and path.is_file():chosen=path;break
                    if chosen is None:warnings.append('Missing/unapproved mesh '+Path(filename).name[:200]);continue
                    record['source_path']=str(chosen);record['scale']=[x*mesh_scale_factor for x in record['scale']]
                elif element.tag=='Brick':record['half_lengths']=numbers(element.findtext('half_lengths'),[.05,.05,.05])
                elif element.tag=='Ellipsoid':record['radii']=numbers(element.findtext('radii'),[.05,.05,.05])
                else:record['radius']=float(element.findtext('radius','.05'))
                if len(records)>=50:raise InputError('At most 50 visual meshes per export.')
                if any(v<0 or v>1 for v in record['color']) or any(v<=0 for v in record['scale']):raise InputError('Invalid geometry color/scale.')
                records.append(record)
        for child in node:
            if child.tag!='attached_geometry':walk(child,current)
    walk(model);return records,warnings

def mesh_data(cfg,records):
    with tempfile.TemporaryDirectory(prefix='viewer-mesh-',dir=cfg.temp_root) as name:
        work=Path(name);staged=[];hashes={};total=0
        for i,record in enumerate(records):
            item=dict(record)
            if item['type']=='mesh':
                path=Path(item.pop('source_path'));raw=bounded_read(path,16*1024**2);hashes[str(i)]=digest(raw);item['source_sha256']=digest(raw);total+=len(raw)
                if total>128*1024**2:raise InputError('Total source mesh size exceeded 128 MiB.')
                if path.suffix.lower()=='.obj':raw=b'\n'.join(line for line in raw.splitlines() if line.strip() and line.split(None,1)[0] in {b'v',b'vn',b'vt',b'f',b'g',b'o',b's'})
                if path.suffix.lower()=='.vtp':
                    document=fromstring(raw)
                    if document.tag!='VTKFile' or document.get('type')!='PolyData' or any(k.lower() in {'file','filename','source','href'} for e in document.iter() for k in e.attrib):raise InputError('Only self-contained VTP PolyData is supported.')
                filename='mesh-'+str(i)+path.suffix.lower();(work/filename).write_bytes(raw);item['staged_file']=filename
            staged.append(item)
        (work/'meshes.json').write_text(json.dumps(staged,allow_nan=False),encoding='utf-8')
        tree=ProcessTree();process=None
        try:
            with (work/'mesh.log').open('wb') as log:
                process=tree.spawn([sys.executable,'-B','-m','opensim_mcp.mesh_worker',str(work)],cwd=work,
                    env=dict(os.environ,TEMP=str(work),TMP=str(work),PYTHONDONTWRITEBYTECODE='1'),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000)
                deadline=time.monotonic()+120
                while process.poll() is None:
                    if time.monotonic()>deadline:raise TimeoutError('Mesh conversion exceeded 120 s.')
                    if (work/'mesh.log').stat().st_size>2*1024**2:raise InputError('Mesh conversion log limit exceeded.')
                    time.sleep(.05)
                if process.returncode:raise InputError('Mesh conversion failed: '+bounded_read(work/'mesh.log',2*1024**2).decode(errors='replace')[-3000:])
            return json.loads(bounded_read(work/'mesh_result.json',32*1024**2)),hashes
        finally:
            if process and process.poll() is None:tree.terminate();process.wait(timeout=10)
            tree.close()

def export_animation(cfg,api,motion_path,geometry_model_path=None,geometry_roots=None,comparison_motion_path=None,marker_path=None,max_frames=200,mesh_scale_factor=1.,error_color_range_m=.03,angles_in_degrees=None,
                     muscle_result_path=None,comparison_muscle_result_path=None,muscle_volume_path=None,muscle_data_interpolation='none'):
    if type(max_frames) is not int or not 2<=max_frames<=300:raise InputError('max_frames must be 2..300.')
    if any(type(v) not in {int,float} or not math.isfinite(v) or v<=0 for v in (mesh_scale_factor,error_color_range_m)):raise InputError('Visual scale/error range must be finite and positive.')
    def motion(path):
        p=local_path(path)
        if p.suffix.lower() not in {'.mot','.sto'}:raise InputError('Motion must be MOT/STO.')
        cfg.input_path(path,p.suffix.lower());t=read_motion(p);flag=t['in_degrees'].lower()
        if flag not in {'yes','no','true','false'}:
            if type(angles_in_degrees) is not bool:raise InputError('Motion requires explicit inDegrees or angles_in_degrees.')
            degree=angles_in_degrees
        else:
            degree=flag in {'yes','true'}
            if angles_in_degrees is not None and (type(angles_in_degrees) is not bool or angles_in_degrees!=degree):raise InputError('Angle declaration conflicts with the motion file.')
        return t,degree
    primary,pd=motion(motion_path);secondary,sd=motion(comparison_motion_path) if comparison_motion_path else (None,False)
    if secondary and (secondary['rows'][0][0]>primary['rows'][0][0] or secondary['rows'][-1][0]<primary['rows'][-1][0]):raise InputError('Comparison must cover the full primary motion.')
    saved=api.save();records,warnings=geometry(cfg,saved['model_file'],geometry_roots,mesh_scale_factor)
    if geometry_model_path:
        extra,other=geometry(cfg,geometry_model_path,geometry_roots,mesh_scale_factor);known={(r['frame'],r['name']) for r in records};records.extend(r for r in extra if (r['frame'],r['name']) not in known);warnings+=other
        warnings.append('Caller supplied visual geometry must match the current physical model, scale and frame identities.')
    if len(records)>50:raise InputError('Combined mesh budget exceeded.')
    # The same integer sampling rule is used by the native worker.
    n=len(primary['rows']);count=min(n,max_frames);indices=sorted(set(int(i*(n-1)/(count-1)) for i in range(count)))
    targets={}
    if marker_path:
        raw=bounded_read(cfg.input_path(marker_path,'.trc'),64*1024**2);info=trc_info(raw);rows=[[float(v) for v in line.split()] for line in raw.decode('utf-8-sig').splitlines()[6:] if line.strip()];factor=.001 if info['units']=='mm' else 1.
        if info['times'][0]>primary['rows'][0][0] or info['times'][-1]<primary['rows'][-1][0]:raise InputError('Experimental markers must cover primary motion; no extrapolation.')
        for index in indices:
            t=primary['rows'][index][0];j=max(0,min(len(rows)-2,bisect.bisect_right(info['times'],t)-1));a,b=rows[j:j+2];w=(t-a[1])/(b[1]-a[1])
            targets[str(index)]={name:[factor*(a[2+3*k+c]+w*(b[2+3*k+c]-a[2+3*k+c])) for c in range(3)] for k,name in enumerate(info['markers'])}
    assets={'motion.sto':motion_path}
    if comparison_motion_path:assets['comparison.sto']=comparison_motion_path
    result=run_native(cfg,'animation_frames',saved['model_file'],dict(frame_paths=sorted(set(r['frame'] for r in records)),max_frames=max_frames,
        primary_degrees=pd,secondary_degrees=sd,has_comparison=bool(secondary),marker_targets=targets,sampled_indices=indices),assets)
    frames=json.loads(bounded_read(Path(next(f for f in result['files'] if Path(f).name=='animation_frames.json')),32*1024**2))
    if frames.get('unavailable_muscles'):warnings.append('Muscles without a geometric path cannot be displayed: '+', '.join(frames['unavailable_muscles'])[:500])
    missing=set(frames['missing_frame_paths']);records=[r for r in records if r['frame'] not in missing];warnings+=['Missing physical frame '+p for p in sorted(missing)]
    meshes,hashes=mesh_data(cfg,records) if records else ([],{})
    data=dict(frames,meshes=meshes,error_color_range_m=error_color_range_m,warnings=warnings,visual_geometry_source_sha256=digest(bounded_read(cfg.input_path(geometry_model_path,'.osim'),MAX_MODEL)) if geometry_model_path else None,
        mesh_source_hashes=hashes,scope='Visual samples/native transforms, not a new dynamics solve or full-trial quality assessment. No textures, external libraries, network fetches or original asset paths are embedded.')
    # Remove private source paths; the provenance keeps hashes by mesh label.
    data['mesh_source_hashes']=hashes
    data['error_reference']='experimental markers' if targets else 'comparison motion' if secondary else None
    from .muscle_display import bind
    bind(cfg,data,digest(bounded_read(cfg.input_path(motion_path,Path(motion_path).suffix.lower()),64*1024**2)),muscle_result_path,comparison_muscle_result_path,muscle_volume_path,muscle_data_interpolation)
    encoded=json.dumps(data,ensure_ascii=True,allow_nan=False).replace('<','\\u003c')
    if len(encoded.encode())>32*1024**2:raise InputError('Viewer payload exceeds 32 MiB.')
    folder=cfg.results_root/('animation-'+uuid.uuid4().hex);folder.mkdir(parents=True);nonce=secrets.token_hex(16)
    template=(Path(__file__).parent/'viewer_assets/player.html').read_text(encoding='utf-8');script=(Path(__file__).parent/'viewer_assets/player.js').read_text(encoding='utf-8')
    html=template.replace('__NONCE__',nonce).replace('__SCRIPT__',script).replace('__DATA__',encoded)
    (folder/'viewer.html').write_text(html,encoding='utf-8');(folder/'animation.json').write_text(json.dumps(data,allow_nan=False),encoding='utf-8')
    output=dict(html_file=str(folder/'viewer.html'),scene_file=str(folder/'animation.json'),frame_count=len(frames['frames']),mesh_count=len(meshes),muscle_count=len(frames.get('muscle_names',[])),source_motion_rows=n,
        comparison_included=bool(secondary),marker_errors_included=bool(targets or secondary),warnings=warnings,scope=data['scope'],api_model_pose_changed=False)
    output['muscle_force_results_included']=bool(data['muscle_result_info'])
    (folder/'provenance.json').write_text(json.dumps(output,indent=2),encoding='utf-8');return output
