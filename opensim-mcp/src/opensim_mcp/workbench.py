"""Portable single/two-scene workbench with declared time matching and view identity."""
from __future__ import annotations
import bisect,json,math,secrets,uuid
from pathlib import Path
from .core import InputError,bounded_read
from .projects import digest
from .visual_signals import validate_scene,component_ids

def number(value,name):
    if type(value) not in {int,float} or not math.isfinite(value):raise InputError(name+' must be finite numeric data.')
    return float(value)

def component(value,scene,kinds=None):
    if not isinstance(value,dict) or set(value)!={'kind','name'} or not all(isinstance(x,str) for x in value.values()):raise InputError('Expected component kind/name.')
    known=component_ids(scene)
    if value['kind'] not in (kinds or known) or value['name'] not in known[value['kind']]:raise InputError('Unknown scene component.')
    return value

def read_scene(cfg,path):
    raw=bounded_read(cfg.input_path(path,'.json'),32*1024**2)
    try:
        scene=validate_scene(json.loads(raw))
        if scene['units']!='m' or not isinstance(scene['coordinate_system'],str):raise InputError('Scene geometry must explicitly be in meters with declared coordinates.')
        for f in scene['frames']:
            for p in f['markers'].values():
                if not isinstance(p,list) or len(p)!=3:raise InputError('Invalid marker coordinates.')
                for v in p:number(v,'marker')
            for k,v in f['coordinate_values'].items():number(v,'coordinate value')
        # Reject NaN even in unused nested fields before creating browser assets.
        json.dumps(scene,allow_nan=False)
    except InputError:raise
    except (ValueError,KeyError,TypeError) as exc:raise InputError('Invalid native scene.') from exc
    return scene,raw

def alignment(entries,max_delta):
    max_delta=number(max_delta,'max_time_delta_s')
    if not 0<=max_delta<=60:raise InputError('max_time_delta_s must be 0..60 seconds.')
    times=[[f['time']+e['time_offset_s'] for f in e['scene']['frames']] for e in entries]
    start=max(t[0] for t in times);end=min(t[-1] for t in times)
    if end<=start:raise InputError('Scenes need a nonzero overlapping declared time range.')
    master=[t for t in times[0] if start-1e-9<=t<=end+1e-9]
    if len(master)<2:raise InputError('Overlap contains fewer than two primary scene samples.')
    table=[]
    for t in master:
        indices=[]
        for samples in times:
            i=bisect.bisect_left(samples,t);near=min((j for j in (i-1,i) if 0<=j<len(samples)),key=lambda j:abs(samples[j]-t))
            indices.append(near if abs(samples[near]-t)<=max_delta+1e-9 else None)
        table.append(indices)
    return dict(times=master,indices=table,max_time_delta_s=max_delta,method='nearest_native_sample_no_interpolation',coverage=[sum(row[i] is not None for row in table) for i in range(len(entries))])

def validate_state(state,entries,view_id,match):
    if not isinstance(state,dict) or state.get('schema')!='opensim_view_state_v1' or state.get('workbench_id')!=view_id:raise InputError('View state belongs to different scene inputs or alignment.')
    if set(state)-{'schema','workbench_id','frame','camera','selected','hidden','opacity','layers','curve','measurement','note'}:raise InputError('Unknown view-state fields.')
    if type(state.get('frame')) is not int or not 0<=state['frame']<len(match['times']):raise InputError('Invalid saved frame.')
    camera=state.get('camera');limits={'yaw':(-100,100),'pitch':(-1.4,1.4),'zoom':(.3,100)}
    if not isinstance(camera,dict) or set(camera)!=set(limits):raise InputError('Invalid saved camera.')
    for k,(lo,hi) in limits.items():
        if not lo<=number(camera[k],'camera')<=hi:raise InputError('Saved camera outside range.')
    selected=state.get('selected')
    if selected is not None:
        if not isinstance(selected,dict) or set(selected)!={'scene','component'} or type(selected['scene']) is not int or not 0<=selected['scene']<len(entries):raise InputError('Invalid selected scene.')
        component(selected['component'],entries[selected['scene']]['scene'])
    hidden=state.get('hidden')
    if not isinstance(hidden,list) or len(hidden)!=len(entries):raise InputError('Invalid hidden components.')
    for values,entry in zip(hidden,entries):
        if not isinstance(values,list) or len(values)>1000:raise InputError('Hidden component limit exceeded.')
        for value in values:component(value,entry['scene'])
    if not .05<=number(state.get('opacity'),'opacity')<=1:raise InputError('Opacity must be .05..1.')
    layers=state.get('layers')
    if not isinstance(layers,dict) or set(layers)!={'surfaces','muscles','markers','skeleton'} or any(type(v) is not bool for v in layers.values()):raise InputError('Invalid visibility settings.')
    curve=state.get('curve')
    if not isinstance(curve,str) or len(curve)>500:raise InputError('Invalid saved curve.')
    known_curves={'coordinate:'+n for n in entries[0]['scene']['coordinate_units']}
    known_curves|={'signal:'+s['id'] for s in entries[0]['scene'].get('external_signals',[])}
    known_curves|={kind+':'+name for name in entries[0]['scene'].get('muscle_names',[]) for kind,field in [('force','muscle_forces_N'),('activation','muscle_activations')] if any(name in f.get(field,{}) for f in entries[0]['scene']['frames'])}
    if curve and curve not in known_curves:raise InputError('Saved curve does not exist.')
    measurement=state.get('measurement')
    if not isinstance(measurement,dict) or set(measurement)!={'scene','points'} or type(measurement['scene']) is not int or not 0<=measurement['scene']<len(entries) or not isinstance(measurement['points'],list) or len(measurement['points'])>3:raise InputError('Invalid measurement.')
    for p in measurement['points']:component(p,entries[measurement['scene']]['scene'],{'frame','marker'})
    note=state.get('note')
    if not isinstance(note,str) or len(note)>1000:raise InputError('Note exceeds 1000 characters.')
    return state

def create_workbench(cfg,scenes,max_time_delta_s,component_mapping=None,view_state_path=None):
    if not isinstance(scenes,list) or not 1<=len(scenes)<=2:raise InputError('Provide one or two scenes.')
    entries=[];total=0
    for spec in scenes:
        if not isinstance(spec,dict) or set(spec)!={'path','label','time_offset_s'} or not isinstance(spec['label'],str) or not 1<=len(spec['label'])<=80:raise InputError('Each scene needs path, short label and explicit time_offset_s.')
        offset=number(spec['time_offset_s'],'time_offset_s')
        if abs(offset)>1e9:raise InputError('Time offset outside range.')
        scene,raw=read_scene(cfg,spec['path']);total+=len(raw)
        if total>32*1024**2:raise InputError('Combined source scenes exceed 32 MiB.')
        entries.append(dict(label=spec['label'],time_offset_s=offset,sha256=digest(raw),scene=scene))
    if len(entries)==2 and entries[0]['scene']['coordinate_system']!=entries[1]['scene']['coordinate_system']:raise InputError('Coordinate conventions differ; transform scenes explicitly before comparing.')
    match=alignment(entries,max_time_delta_s);mapping=component_mapping or []
    if not isinstance(mapping,list) or len(mapping)>500 or (mapping and len(entries)!=2):raise InputError('Component mappings require two scenes; maximum 500.')
    used=[set(),set()]
    for item in mapping:
        if not isinstance(item,dict) or set(item)!={'left','right'}:raise InputError('Mapping needs left and right components.')
        for i,key in enumerate(('left','right')):
            c=component(item[key],entries[i]['scene']);ident=(c['kind'],c['name'])
            if ident in used[i]:raise InputError('Component mapping must be one-to-one.')
            used[i].add(ident)
        if item['left']['kind']!=item['right']['kind']:raise InputError('Mapped component kinds must match.')
        if item['left']['kind']=='coordinate' and entries[0]['scene']['coordinate_units'][item['left']['name']]!=entries[1]['scene']['coordinate_units'][item['right']['name']]:raise InputError('Mapped coordinate units differ; no implicit unit conversion.')
    view_id=digest(json.dumps(dict(sources=[dict(sha256=e['sha256'],time_offset_s=e['time_offset_s']) for e in entries],max_delta=match['max_time_delta_s'],mapping=mapping),sort_keys=True).encode())
    state=None
    if view_state_path:
        try:state=validate_state(json.loads(bounded_read(cfg.input_path(view_state_path,'.json'),256*1024)),entries,view_id,match)
        except InputError:raise
        except (ValueError,KeyError,TypeError) as exc:raise InputError('Invalid saved view state.') from exc
    data=dict(schema='opensim_workbench_data_v1',id=view_id,entries=entries,alignment=match,component_mapping=mapping,initial_state=state)
    folder=cfg.results_root/('workbench-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    assets={};nonce=secrets.token_hex(16);base=Path(__file__).parent/'viewer_assets'
    embedded=[]
    for i,entry in enumerate(entries):
        original=dict(entry['scene']);original['workbench_embedded']=True;original['workbench_channel']=nonce+'-'+str(i)
        encoded=json.dumps(original,ensure_ascii=True,allow_nan=False).replace('<','\\u003c')
        embedded.append((base/'player.html').read_text(encoding='utf-8').replace('__NONCE__',nonce).replace('__SCRIPT__',(base/'player.js').read_text(encoding='utf-8')).replace('__DATA__',encoded))
        path=folder/('scene-'+str(i)+'.json');path.write_text(json.dumps(entry['scene'],allow_nan=False),encoding='utf-8');assets[path.name]=digest(path.read_bytes())
    data.update(embedded=embedded,channel=nonce)
    template=(base/'workbench.html').read_text(encoding='utf-8');script=(base/'workbench.js').read_text(encoding='utf-8')
    (folder/'viewer.html').write_text(template.replace('__NONCE__',nonce).replace('__SCRIPT__',script).replace('__DATA__',json.dumps(data,ensure_ascii=True,allow_nan=False).replace('<','\\u003c')),encoding='utf-8')
    assets['viewer.html']=digest((folder/'viewer.html').read_bytes())
    manifest=dict(schema='opensim_visual_workbench_v1',workbench_id=view_id,assets=assets,scenes=[{k:v for k,v in e.items() if k!='scene'} for e in entries],alignment=match,component_mapping=mapping,scope='Offline views; nearest declared native samples only. Same-name selection is identifier matching, not physical equivalence. Marker/frame-origin measures are not anatomical joint angles or mesh clearance.')
    path=folder/'visualization.json';path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return dict(status='completed',html_file=str(folder/'viewer.html'),project_file=str(path),workbench_id=view_id,scene_count=len(entries),aligned_frames=len(match['times']),matched_frames=match['coverage'],scope=manifest['scope'])
