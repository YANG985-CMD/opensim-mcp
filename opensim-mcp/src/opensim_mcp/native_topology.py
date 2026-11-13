"""Apply original structured XML/object edits, then validate in an isolated native process."""
import math
from pathlib import Path
from xml.etree import ElementTree as ET

SETS={'bodyset':('BodySet','Body'),'jointset':('JointSet',None),'markerset':('MarkerSet','Marker'),'forceset':('ForceSet',None)}

def vector(value,size=3,positive=False):
    if not isinstance(value,list) or len(value)!=size or any(type(v) not in {int,float} or not math.isfinite(v) or abs(v)>1e9 or (positive and v<=0) for v in value):raise ValueError('Invalid finite physical vector.')
    return value

def number(value,positive=False):
    if type(value) not in {int,float} or not math.isfinite(value) or abs(value)>1e9 or (positive and value<=0):raise ValueError('Invalid physical scalar.')
    return float(value)

def run(osim,p):
    tree=ET.parse('model.osim');model=tree.getroot().find('Model');renames=[];changes=[]
    def objects(kind):
        tag,_=SETS[kind];entry=model.find(tag)
        if entry is None:entry=ET.SubElement(model,tag)
        found=entry.find('objects')
        if found is None:found=ET.SubElement(entry,'objects')
        return found
    def unique(kind,name):
        if any(x.get('name')==name for x in objects(kind)):raise ValueError('Component name already exists: '+name)
    def locate(path):
        parts=path.strip('/').split('/')
        if len(parts)!=2 or parts[0] not in SETS:raise ValueError('Only whole body/joint/marker/force set members may be removed/renamed.')
        matches=[x for x in objects(parts[0]) if x.get('name')==parts[1]]
        if len(matches)!=1:raise ValueError('Component path missing/ambiguous: '+path)
        return parts[0],matches[0]
    def rewrite(old,new):
        for e in model.iter():
            if e.text and e.text.strip():
                tokens=e.text.split();changed=False
                for i,value in enumerate(tokens):
                    if value==old or value.startswith(old+'/'):tokens[i]=new+value[len(old):];changed=True
                if changed:e.text=' '.join(tokens)
    def frame(joint,which,path):
        socket=joint.find('socket_'+which+'_frame')
        if socket is None:raise ValueError('Joint frame socket is missing.')
        name=(socket.text or '').strip().split('/')[-1]
        candidates=[e for e in joint.iter('PhysicalOffsetFrame') if e.get('name')==name]
        if candidates:
            parent=candidates[0].find('socket_parent')
            if parent is None:raise ValueError('Unsupported offset-frame representation.')
            parent.text=path
        else:socket.text=path
    for operation in p['operations']:
        op=operation['op']
        if op=='add_body':
            name=operation['name'];unique('bodyset',name);body=osim.Body(name,number(operation['mass'],True),osim.Vec3(*vector(operation['mass_center'])),osim.Inertia(*vector(operation['inertia'],6)))
            if operation.get('geometry'):
                g=operation['geometry'];kind=g.get('type')
                if kind=='brick' and set(g)<={'type','half_lengths','color'}:geometry=osim.Brick(osim.Vec3(*vector(g['half_lengths'],positive=True)))
                elif kind=='sphere' and set(g)<={'type','radius','color'}:geometry=osim.Sphere(number(g['radius'],True))
                elif kind=='ellipsoid' and set(g)<={'type','radii','color'}:geometry=osim.Ellipsoid(osim.Vec3(*vector(g['radii'],positive=True)))
                else:raise ValueError('Supported geometry is brick/sphere/ellipsoid with explicit SI sizes.')
                color=vector(g.get('color',[.3,.5,.7]))
                if any(v<0 or v>1 for v in color):raise ValueError('Color must be in [0,1].')
                geometry.setName('visual_'+name);geometry.setColor(osim.Vec3(*color));body.attachGeometry(geometry)
            objects('bodyset').append(ET.fromstring(body.dump()))
        elif op=='add_joint':
            name=operation['name'];unique('jointset',name);kind=operation['joint_type'];joint=getattr(osim,kind)();joint.setName(name)
            if kind!='WeldJoint':
                c=operation.get('coordinate')
                if not isinstance(c,dict) or set(c)-{'name','default_value','range','locked','clamped'} or not {'name','range','default_value'}<=c.keys():raise ValueError('Pin/Slider joint requires explicit coordinate name, range and default value.')
                if any(e.get('name')==c['name'] for e in model.iter('Coordinate')):raise ValueError('Coordinate name must be globally unique.')
                bounds=vector(c['range'],2)
                if bounds[0]>=bounds[1] or not bounds[0]<=number(c['default_value'])<=bounds[1]:raise ValueError('Invalid coordinate range/default.')
                coord=joint.updCoordinate();coord.setName(c['name']);coord.setRangeMin(bounds[0]);coord.setRangeMax(bounds[1]);coord.setDefaultValue(c['default_value'])
                for key,method in [('locked','setDefaultLocked'),('clamped','setDefaultClamped')]:
                    if type(c.get(key,False)) is not bool:raise ValueError('Coordinate flags must be boolean.')
                    getattr(coord,method)(c.get(key,False))
            elif 'coordinate' in operation:raise ValueError('WeldJoint has no coordinate.')
            element=ET.fromstring(joint.dump());frames=element.find('frames')
            if frames is None:frames=ET.SubElement(element,'frames')
            for side,parent in [('parent',operation['parent_frame']),('child','/bodyset/'+operation['child_body'])]:
                offset=osim.PhysicalOffsetFrame();offset.setName(side+'_offset')
                offset.set_translation(osim.Vec3(*vector(operation.get('location_in_'+side,[0.,0.,0.]))));offset.set_orientation(osim.Vec3(*vector(operation.get('orientation_in_'+side,[0.,0.,0.]))))
                item=ET.fromstring(offset.dump());parent_socket=item.find('socket_parent')
                if parent_socket is None:parent_socket=ET.SubElement(item,'socket_parent')
                parent_socket.text=parent;frames.append(item)
                socket=element.find('socket_'+side+'_frame')
                if socket is None:socket=ET.SubElement(element,'socket_'+side+'_frame')
                socket.text=side+'_offset'
            objects('jointset').append(element)
        elif op=='add_marker':
            unique('markerset',operation['name']);marker=osim.Marker();marker.setName(operation['name']);marker.set_location(osim.Vec3(*vector(operation['location'])))
            element=ET.fromstring(marker.dump());socket=element.find('socket_parent_frame')
            if socket is None:socket=ET.SubElement(element,'socket_parent_frame')
            socket.text=operation['parent_frame'];objects('markerset').append(element)
        elif op=='add_coordinate_actuator':
            unique('forceset',operation['name'])
            if not any(c.get('name')==operation['coordinate'] for c in model.iter('Coordinate')):raise ValueError('Actuator coordinate is missing.')
            a=osim.CoordinateActuator(operation['coordinate']);a.setName(operation['name']);a.setOptimalForce(number(operation['optimal_force'],True))
            low,high=number(operation['min_control']),number(operation['max_control'])
            if low>=high:raise ValueError('Actuator bounds must be ordered.')
            a.setMinControl(low);a.setMaxControl(high);objects('forceset').append(ET.fromstring(a.dump()))
        elif op in {'remove_component','rename_component'}:
            path=operation['component_path'];kind,element=locate(path);old=element.get('name')
            if op=='remove_component':objects(kind).remove(element);new=None
            else:
                new=operation['new_name'];unique(kind,new);element.set('name',new);new_path='/'+kind+'/'+new;rewrite(path,new_path);renames.append([path,new_path])
            for members in model.findall(SETS[kind][0]+'/groups//members'):
                tokens=(members.text or '').split();members.text=' '.join((new if x==old else x) for x in tokens if x!=old or new is not None)
        elif op=='reconnect_joint':
            _,joint=locate('/jointset/'+operation['joint_name'])
            if joint.tag not in {'PinJoint','SliderJoint','WeldJoint'}:raise ValueError('Reconnection supports Pin/Slider/Weld joints only.')
            frame(joint,'parent',operation['parent_frame'])
            if 'child_body' in operation:frame(joint,'child','/bodyset/'+operation['child_body'])
        else:raise ValueError('Unsupported topology operation.')
        changes.append({'op':op,'native_candidate_only':True})
    tree.write('candidate.osim',encoding='utf-8',xml_declaration=True)
    candidate=osim.Model('candidate.osim');candidate.finalizeConnections();bodies={candidate.getBodySet().get(i).getName() for i in range(candidate.getBodySet().getSize())};parents={}
    for i in range(candidate.getJointSet().getSize()):
        joint=candidate.getJointSet().get(i);child=joint.getChildFrame().findBaseFrame().getName();parent=joint.getParentFrame().findBaseFrame().getName()
        if child in parents:raise ValueError('Joint child body has multiple tree parents.')
        parents[child]=parent
    if set(parents)!=bodies:raise ValueError('Every body must have one explicit joint; implicit free joints are not accepted.')
    for body in bodies:
        seen=set();current=body
        while current!='ground':
            if current in seen or current not in parents:raise ValueError('Joint tree is cyclic/disconnected.')
            seen.add(current);current=parents[current]
    state=candidate.initSystem();candidate.realizePosition(state);candidate.printToXML('model.osim')
    return dict(outputs=['model.osim'],renames=renames,changes=changes,opensim_version=osim.GetVersionAndDate(),
        quality=dict(native_initialized=True,total_mass_kg=candidate.getTotalMass(state),body_count=len(bodies),joint_count=candidate.getJointSet().getSize(),marker_count=candidate.getMarkerSet().getSize(),coordinate_count=candidate.getCoordinateSet().getSize()))
