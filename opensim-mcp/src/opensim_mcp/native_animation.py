"""Sample native transforms, markers and muscle geometry on an isolated copy."""
import json,math
from pathlib import Path

def muscle_path_points(osim, path, state, max_points=2048):
    """Use the native active path, including moving/conditional and wrap points."""
    active=path.getCurrentPath(state);positions=[]
    if active.getSize()>max_points:raise ValueError('Muscle path point budget exceeded.')
    def append(vector):
        point=[float(vector.get(i)) for i in range(3)]
        if any(not math.isfinite(v) for v in point):raise ValueError('Nonfinite muscle path location.')
        if not positions or sum((a-b)**2 for a,b in zip(point,positions[-1]))>1e-20:positions.append(point)
        if len(positions)>max_points:raise ValueError('Muscle path point budget exceeded.')
    for index in range(active.getSize()):
        point=active.get(index);wrap=osim.PathWrapPoint.safeDownCast(point)
        surface=wrap.getWrapPath(state) if wrap is not None else None
        if surface is not None and surface.getSize():
            if surface.getSize()>max_points:raise ValueError('Muscle wrap point budget exceeded.')
            parent=wrap.getParentFrame()
            for j in range(surface.getSize()):append(parent.findStationLocationInGround(state,surface.get(j)))
        else:append(point.getLocationInGround(state))
    if len(positions)<2:raise ValueError('Muscle path must contain two distinct active locations.')
    return positions

def run(osim,p):
    import numpy as np
    try:from .native_muscle import fingerprint
    except ImportError:from native_muscle import fingerprint
    model=osim.Model('model.osim');model.finalizeConnections();state=model.initSystem()
    physics_signature=fingerprint(model)
    def read_table(filename):
        lines=Path(filename).read_text(encoding='utf-8-sig').splitlines();end=next(i for i,line in enumerate(lines) if line.strip().lower()=='endheader')
        data=[line.split() for line in lines[end+1:] if line.strip()];return data[0],np.asarray([[float(v) for v in row] for row in data[1:]],dtype=float)
    labels,matrix=read_table('motion.sto');times=matrix[:,0].tolist()
    coordinates=[model.getCoordinateSet().get(i) for i in range(model.getCoordinateSet().getSize())]
    def columns(data):
        names,matrix=data;result={}
        for c in coordinates:
            short=c.getName();path=c.getAbsolutePathString()+'/value';key=short if short in names else path
            if key not in names:raise ValueError('Animation motion omits coordinate '+short)
            result[short]=matrix[:,names.index(key)]
        return result
    primary=columns((labels,matrix));comparison=read_table('comparison.sto') if p['has_comparison'] else None
    secondary=columns(comparison) if comparison else None;secondary_times=comparison[1][:,0].tolist() if comparison else None
    indices=p['sampled_indices']
    paths=sorted(set(['/ground']+[model.getBodySet().get(i).getAbsolutePathString() for i in range(model.getBodySet().getSize())]+p['frame_paths']))
    frames={};missing=[];frame_to_body={}
    if len(paths)>500:raise ValueError('Animation frame budget exceeded.')
    for path in paths:
        try:
            frame=model.getGround() if path=='/ground' else osim.PhysicalFrame.safeDownCast(model.getComponent(path))
            if frame is None:raise ValueError('Not a physical frame.')
            frames[path]=frame;frame_to_body[path]=frame.findBaseFrame().getAbsolutePathString()
        except Exception:missing.append(path)
    markers=[model.getMarkerSet().get(i) for i in range(min(500,model.getMarkerSet().getSize()))]
    marker_bodies={m.getName():m.getParentFrame().findBaseFrame().getAbsolutePathString() for m in markers}
    muscle_set=model.getMuscles();muscles=[];unavailable=[];sample_count=0
    if muscle_set.getSize()>300:raise ValueError('Animation supports at most 300 muscles.')
    for i in range(muscle_set.getSize()):
        muscle=muscle_set.get(i)
        try:path=muscle.getGeometryPath()
        except Exception:
            unavailable.append(muscle.getName());continue
        muscles.append((muscle.getName(),path))
    links=[]
    for i in range(model.getJointSet().getSize()):
        j=model.getJointSet().get(i);links.append([j.getParentFrame().findBaseFrame().getAbsolutePathString(),j.getChildFrame().findBaseFrame().getAbsolutePathString()])
    def capture(values,t,degrees):
        nonlocal sample_count
        q={}
        for c in coordinates:
            v=float(values[c.getName()]);v=math.radians(v) if degrees and c.getMotionType()==1 else v;c.setValue(state,v,False);q[c.getName()]=v
        state.setTime(t);model.assemble(state);model.realizePosition(state);transforms={}
        for path,frame in frames.items():
            transform=frame.getTransformInGround(state);rotation=transform.R();translation=transform.p()
            matrix=[float(rotation.get(r,c)) if r<3 and c<3 else float(translation.get(r)) if c==3 and r<3 else 1. if r==3 and c==3 else 0. for c in range(4) for r in range(4)]
            transforms[path]=matrix
        positions={}
        for marker in markers:
            pos=marker.getLocationInGround(state);positions[marker.getName()]=[float(pos.get(i)) for i in range(3)]
        muscle_paths={};muscle_lengths={}
        for name,path in muscles:
            muscle_paths[name]=muscle_path_points(osim,path,state)
            length=float(path.getLength(state))
            if not math.isfinite(length) or length<=0:raise ValueError('Invalid native muscle path length: '+name)
            muscle_lengths[name]=length;sample_count+=len(muscle_paths[name])
            if sample_count>400000:raise ValueError('Animation muscle sample budget exceeded; reduce max_frames.')
        return dict(time=t,transforms=transforms,markers=positions,coordinate_values=q,muscle_paths=muscle_paths,muscle_lengths_m=muscle_lengths)
    animation=[];compare=[]
    for index in indices:
        t=float(times[index]);item=capture({n:values[index] for n,values in primary.items()},t,p['primary_degrees'])
        if comparison:
            if t<secondary_times[0]-1e-9 or t>secondary_times[-1]+1e-9:raise ValueError('Comparison does not cover animation window.')
            other=capture({n:float(np.interp(t,secondary_times,v)) for n,v in secondary.items()},t,p['secondary_degrees']);compare.append(other)
            item['marker_errors_m']={n:math.sqrt(sum((position[k]-other['markers'][n][k])**2 for k in range(3))) for n,position in item['markers'].items()}
        if p['marker_targets']:
            target=p['marker_targets'][str(index)];item['marker_errors_m']={n:math.sqrt(sum((item['markers'][n][k]-v[k])**2 for k in range(3))) for n,v in target.items() if n in item['markers']}
        animation.append(item)
    result=dict(name=model.getName(),frames=animation,comparison_frames=compare,frame_to_body=frame_to_body,marker_bodies=marker_bodies,
        joint_links=links,missing_frame_paths=missing,source_rows=len(times),sampled_indices=indices,coordinate_units={c.getName():'rad' if c.getMotionType()==1 else 'm' for c in coordinates},
        units='m',coordinate_system='OpenSim X/Y/Z, Y up',interpolation='Comparison/TRC linear interpolation, no extrapolation. Primary frames sampled without interpolation.',
        muscle_names=[name for name,path in muscles],unavailable_muscles=unavailable,physics_signature=physics_signature,
        muscle_visualization_scope='Native active muscle paths and wrap surface samples in ground coordinates. Tube thickness is illustrative, not anatomical volume, activation or force.')
    Path('animation_frames.json').write_text(json.dumps(result,allow_nan=False),encoding='utf-8')
    return dict(outputs=['animation_frames.json'],quality={'native_position_frames':len(animation),'source_rows':len(times),'missing_frame_count':len(missing),'muscle_count':len(muscles),'unavailable_muscle_count':len(unavailable)},opensim_version=osim.GetVersionAndDate())
