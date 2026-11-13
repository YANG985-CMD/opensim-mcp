"""Native SI body assembly and rigid landmark alignment; no supplied Python."""
import json,math
from pathlib import Path

def run(osim,p):
    import numpy as np
    model=osim.Model('model.osim');state=model.initSystem();before=model.getTotalMass(state)
    components=[];links=[]
    for item in p['links']:
        name=item['name'];parent=osim.PhysicalFrame.safeDownCast(model.getComponent(item['parent_frame']))
        if parent is None:raise ValueError('Wearable parent is not a PhysicalFrame.')
        rotation=osim.Rotation();rotation.setRotationToBodyFixedXYZ(osim.Vec3(*item['orientation_xyz_rad']))
        translation=np.asarray(item['translation_m'],dtype=float);scale=1.;fit=None
        if 'landmarks' in item:
            lm=item['landmarks'];a=np.asarray(lm['cad_points'],dtype=float)*item['unit_scale'];b=np.asarray(lm['parent_points_m'],dtype=float)
            ac=a-a.mean(axis=0);bc=b-b.mean(axis=0)
            if np.linalg.matrix_rank(ac,tol=1e-10)<2 or np.linalg.matrix_rank(bc,tol=1e-10)<2:raise ValueError('Landmark points must not be collinear/coincident.')
            u,s,v=np.linalg.svd(ac.T@bc);correction=np.eye(3);correction[2,2]=np.linalg.det(v.T@u.T);r=v.T@correction@u.T
            if lm['allow_uniform_scale']:
                scale=float(np.sum(s*np.diag(correction))/np.sum(ac*ac))
                if not .1<=scale<=10:raise ValueError('Uniform fit scale outside [0.1,10].')
            translation=b.mean(axis=0)-scale*r@a.mean(axis=0);errors=np.linalg.norm(scale*(r@a.T).T+translation-b,axis=1)
            matrix=osim.Mat33()
            for i in range(3):
                for j in range(3):matrix.set(i,j,float(r[i,j]))
            rotation=osim.Rotation(matrix);fit=dict(rms_m=float(np.sqrt(np.mean(errors**2))),max_m=float(errors.max()),points=len(a),proper_rotation_determinant=float(np.linalg.det(r)))
            if p['max_landmark_error_m'] is not None and fit['max_m']>p['max_landmark_error_m']:raise ValueError('Landmark fit exceeds configured maximum error.')
        angles=rotation.convertRotationToBodyFixedXYZ();angles=[float(angles.get(i)) for i in range(3)]
        if p['physical']:
            if model.getBodySet().contains(name) or model.getJointSet().contains(name+'_mount'):raise ValueError('Wearable component name collision.')
            body=osim.Body(name,item['mass_kg'],osim.Vec3(*item['mass_center_m']),osim.Inertia(*item['inertia_kg_m2']))
            child_location=item.get('joint_location_in_child_m',[0.,0.,0.]);child_angles=item.get('joint_orientation_in_child_xyz_rad',[0.,0.,0.])
            child_rotation=osim.Rotation();child_rotation.setRotationToBodyFixedXYZ(osim.Vec3(*child_angles))
            parent_r=np.asarray([[rotation.get(i,j) for j in range(3)] for i in range(3)],dtype=float)
            child_r=np.asarray([[child_rotation.get(i,j) for j in range(3)] for i in range(3)],dtype=float)
            joint_r=parent_r@child_r;joint_position=translation+parent_r@np.asarray(child_location)
            joint_matrix=osim.Mat33()
            for i in range(3):
                for j in range(3):joint_matrix.set(i,j,float(joint_r[i,j]))
            joint_orientation=osim.Rotation(joint_matrix).convertRotationToBodyFixedXYZ()
            joint=getattr(osim,item['joint_type'])(name+'_mount',parent,osim.Vec3(*map(float,joint_position)),joint_orientation,body,osim.Vec3(*child_location),osim.Vec3(*child_angles))
            if item['joint_type']!='WeldJoint':
                info=item['coordinate'];coordinate=joint.updCoordinate();coordinate.setName(info['name']);coordinate.setRangeMin(info['range'][0]);coordinate.setRangeMax(info['range'][1]);coordinate.setDefaultValue(info['default_value'])
            model.addBody(body);model.addJoint(joint);model.finalizeConnections();state=model.initSystem()
            components.extend([dict(set='BodySet',xml=str(body.dump())),dict(set='JointSet',xml=str(joint.dump()))])
            if 'coupling' in item:
                coupling=item['coupling'];independent=model.getCoordinateSet().get(coupling['independent_coordinate']);dependent=model.getCoordinateSet().get(item['coordinate']['name'])
                if independent.getMotionType()!=dependent.getMotionType():raise ValueError('Coupled coordinates must have the same native motion units.')
                constraint=osim.CoordinateCouplerConstraint();constraint.setName(name+'_coupling');names=osim.ArrayStr();names.append(coupling['independent_coordinate']);constraint.setIndependentCoordinateNames(names);constraint.setDependentCoordinateName(item['coordinate']['name']);constraint.setFunction(osim.LinearFunction(coupling['scale'],coupling['offset']));model.addConstraint(constraint)
                model.finalizeConnections();state=model.initSystem();model.assemble(state);components.append(dict(set='ConstraintSet',xml=str(constraint.dump())))
            frame_path='/bodyset/'+name
        else:
            frame=osim.PhysicalOffsetFrame();frame.setName(name+'_visual_frame');frame.setParentFrame(parent);frame.set_translation(osim.Vec3(*map(float,translation)));frame.set_orientation(osim.Vec3(*angles));model.addComponent(frame);model.finalizeConnections();state=model.initSystem()
            components.append(dict(set='',xml=str(frame.dump())));frame_path='/'+frame.getName()
        links.append(dict(name=name,parent_frame=item['parent_frame'],frame_path=frame_path,translation_m=translation.tolist(),orientation_xyz_rad=angles,
            uniform_scale=scale,landmark_fit=fit,joint_type=item.get('joint_type'),coordinate=item.get('coordinate'),coupling=item.get('coupling'),
            joint_location_in_child_m=item.get('joint_location_in_child_m'),joint_orientation_in_child_xyz_rad=item.get('joint_orientation_in_child_xyz_rad'),transform_reference='CAD body frame at device coordinate zero; default/coupled coordinate changes the pose.'))
    state=model.initSystem();model.assemble(state);after=model.getTotalMass(state)
    expected=before+sum(item.get('mass_kg',0.) for item in p['links'])
    if abs(after-expected)>1e-8*max(1.,expected):raise ValueError('Combined native model mass mismatch.')
    coordinates=model.getCoordinateSet()
    report=dict(components=components,links=links,coordinate_types={coordinates.get(i).getName():int(coordinates.get(i).getMotionType()) for i in range(coordinates.getSize())},quality=dict(native_initialized_and_assembled=True,original_mass_kg=before,combined_mass_kg=after,
        added_device_mass_kg=after-before,mass_balance_error_kg=after-expected,body_count=model.getBodySet().getSize(),coordinate_count=model.getCoordinateSet().getSize(),constraint_count=model.getConstraintSet().getSize()))
    model.printToXML('assembled_model.osim');reopened=osim.Model('assembled_model.osim');reopened.initSystem()
    if p['physical']:
        verified=[]
        for item in p['links']:
            loaded=reopened.getBodySet().get(item['name']);inertia=loaded.getInertia()
            moments=inertia.getMoments();products=inertia.getProducts();center=loaded.getMassCenter()
            actual={'mass_kg':float(loaded.getMass()),'mass_center_m':[float(center.get(i)) for i in range(3)],
                    'inertia_kg_m2':[float(moments.get(i)) for i in range(3)]+[float(products.get(i)) for i in range(3)]}
            for field in ('mass_kg','mass_center_m','inertia_kg_m2'):
                expected=item[field] if isinstance(item[field],list) else [item[field]]
                values=actual[field] if isinstance(actual[field],list) else [actual[field]]
                tolerance=1e-10*max(max(abs(v) for v in expected),1e-15)
                if any(abs(a-b)>tolerance for a,b in zip(values,expected)):raise ValueError('Reopened native body mass properties differ: '+item['name']+' '+field)
            verified.append(dict(name=item['name'],**actual))
        report['reopened_body_mass_properties']=verified
        report['quality']['reopened_mass_com_inertia_verified']=True
    Path('wearable_components.json').write_text(json.dumps(report,allow_nan=False),encoding='utf-8')
    return dict(outputs=['wearable_components.json','assembled_model.osim'],quality=report['quality'],opensim_version=osim.GetVersionAndDate())
