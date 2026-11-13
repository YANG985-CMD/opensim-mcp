"""Reference-driven Moco implementations, isolated from transport and interactive state."""
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET


def prepare(osim,p):
    import numpy as np
    model=osim.Model('model.osim');model.finalizeConnections();model.initSystem()
    # MOT/STO accepted by the public validator may use spaces. The native
    # DelimFileAdapter requires tabs, so normalize only the private staged copy.
    source=Path('reference.mot');lines=source.read_text(encoding='utf-8-sig').splitlines();end=next(i for i,line in enumerate(lines) if line.strip().lower()=='endheader')
    source.write_text('\n'.join(lines[:end+1]+['\t'.join(line.split()) for line in lines[end+1:] if line.strip()])+'\n',encoding='utf-8')
    table=osim.TimeSeriesTable('reference.mot')
    # Read the explicit file declaration. Legacy Storage can assume degrees for old MOT headers.
    degree_flag=None
    for line in Path('reference.mot').read_text(encoding='utf-8-sig').splitlines():
        if line.strip().lower()=='endheader':break
        if '=' in line and line.split('=',1)[0].strip().lower()=='indegrees':degree_flag=line.split('=',1)[1].strip().lower()
    if degree_flag not in {'yes','no','true','false'}:raise ValueError('Explicit reference angle units required.')
    labels=list(table.getColumnLabels());times=np.asarray(table.getIndependentColumn(),dtype=float)
    names=[];values=[];units={};coordinates=model.getCoordinateSet()
    for i in range(coordinates.getSize()):
        coordinate=coordinates.get(i);name=coordinate.getName();column=table.getDependentColumn(name)
        numbers=np.asarray([column[j] for j in range(table.getNumRows())],dtype=float)
        if degree_flag in {'yes','true'} and coordinate.getMotionType()==1:numbers=np.deg2rad(numbers)
        names.append(coordinate.getAbsolutePathString()+'/value');values.append(numbers)
        units[name]='rad' if coordinate.getMotionType()==1 else ('m' if coordinate.getMotionType()==2 else 'native')
    matrix=np.asarray(values).T
    with Path('reference_states.sto').open('w',encoding='utf-8') as stream:
        stream.write('Reference\nversion=1\nnRows='+str(len(times))+'\nnColumns='+str(len(names)+1)+'\ninDegrees=no\nendheader\n')
        stream.write('\t'.join(['time']+names)+'\n')
        for t,row in zip(times,matrix):stream.write('\t'.join(format(float(v),'.17g') for v in [t]+list(row))+'\n')
    processor=osim.ModelProcessor(model)
    if p['external_forces']:
        root=ET.Element('OpenSimDocument',Version='40000');loads=ET.SubElement(root,'ExternalLoads',name='explicit_loads')
        objects=ET.SubElement(loads,'objects');ET.SubElement(loads,'groups')
        for force in p['external_forces']:
            item=ET.SubElement(objects,'ExternalForce',name=force['name'])
            for key,value in force.items():
                if key!='name':ET.SubElement(item,key).text=value
        ET.SubElement(loads,'datafile').text='loads.sto'
        ET.ElementTree(root).write('external_loads.xml',encoding='utf-8',xml_declaration=True)
        processor.append(osim.ModOpAddExternalLoads('external_loads.xml'))
    return model,processor,times,names,matrix,units


def finish(osim,solution,p,model,reference_times,reference_names,reference_values,units,kind):
    import numpy as np
    if not solution.success():raise RuntimeError('Moco failed: '+solution.getStatus())
    times=np.asarray(solution.getTimeMat(),dtype=float).reshape(-1)
    states=np.asarray(solution.getStatesTrajectoryMat(),dtype=float);controls=np.asarray(solution.getControlsTrajectoryMat(),dtype=float)
    if not np.isfinite(times).all() or not np.isfinite(states).all() or not np.isfinite(controls).all():raise ValueError('Nonfinite Moco result.')
    if len(times)<2 or not np.all(np.diff(times)>0) or abs(times[0]-p['initial_time'])>1e-7 or abs(times[-1]-p['final_time'])>1e-7:raise ValueError('Invalid Moco output time coverage.')
    quality={'solver_success':True,'solver_status':solution.getStatus(),'iterations':solution.getNumIterations(),
             'objective':solution.getObjective(),'rows':len(times),'mesh_interval_s':p['mesh_interval'],'mesh_stability_assessed':False}
    if not math.isfinite(quality['objective']):raise ValueError('Nonfinite objective.')
    state_names=list(solution.getStateNames());control_names=list(solution.getControlNames());fit={}
    for index,name in enumerate(reference_names):
        short=name.split('/')[-2]
        if name not in state_names:raise ValueError('Moco solution omits prescribed/tracked coordinate '+name)
        expected=np.interp(times,reference_times,reference_values[:,index]);errors=states[:,state_names.index(name)]-expected
        fit[short]={'rms':float(np.sqrt(np.mean(errors**2))),'max_abs':float(np.max(np.abs(errors))),'unit':units[short]}
    quality['coordinate_fit']=fit;quality['reference_comparison']='Linear interpolation to solver nodes; no extrapolation; rad/m.'
    if kind=='moco_track':
        if set(p['max_tracking_rms'])-set(fit):raise ValueError('Unknown coordinate RMS threshold.')
        for name,limit in p['max_tracking_rms'].items():
            if fit[name]['rms']>limit:raise ValueError('Tracking RMS exceeds caller threshold: '+name)
        violation=0.;endpoint=0.
        for names,matrix,bounds in [(state_names,states,p['state_bounds']),(control_names,controls,p['control_bounds'])]:
            if set(names)!=set(bounds):raise ValueError('Bounds must cover all native states and controls.')
            for i,name in enumerate(names):
                info=bounds[name];limits=info['bounds'] if isinstance(info,dict) else info
                violation=max(violation,float(np.max(np.maximum(limits[0]-matrix[:,i],matrix[:,i]-limits[-1]))),0.)
                if isinstance(info,dict):
                    for row,key in [(0,'initial'),(-1,'final')]:
                        if key in info:
                            b=info[key];endpoint=max(endpoint,b[0]-float(matrix[row,i]),float(matrix[row,i])-b[-1],0.)
        quality.update(max_bound_violation=violation,max_endpoint_bound_violation=endpoint)
        if max(violation,endpoint)>max(1e-7,10*p['constraint_tolerance']):raise ValueError('Moco bound/endpoint violation.')
    else:
        violations={}
        for i,name in enumerate(control_names):
            # Native actuator bounds, with no implicit reserve insertion.
            component=model.getComponent(name);actuator=osim.ScalarActuator.safeDownCast(component)
            if actuator:
                violations[name]=max(0.,float(np.max(np.maximum(actuator.getMinControl()-controls[:,i],controls[:,i]-actuator.getMaxControl()))))
        quality['max_control_bound_violation']=max(violations.values()) if violations else None
        if quality['max_control_bound_violation'] is not None and quality['max_control_bound_violation']>max(1e-7,10*p['constraint_tolerance']):raise ValueError('MocoInverse control bounds violated.')
        quality['prescribed_kinematics_note']='MocoInverse may assemble constraints; differences include spline versus linear reference interpolation. Review coordinate_fit; no exact reference match is asserted.'
    solution.write('solution.sto');osim.STOFileAdapter.write(solution.exportToStatesTable(),'states.sto');osim.STOFileAdapter.write(solution.exportToControlsTable(),'controls.sto')
    Path('quality.json').write_text(json.dumps(quality,allow_nan=False),encoding='utf-8')
    return {'outputs':['solution.sto','states.sto','controls.sto','quality.json','reference_states.sto','tool.xml'],
            'quality':quality,'opensim_version':osim.GetVersionAndDate(),
            'scope':kind+': explicit reference, external-load assumption and bounded solver; native convergence and sampled quantities only. No automatic reserve actuators, clinical acceptance or mesh-convergence claim.'}


def run(osim,kind,p):
    model,processor,times,names,values,units=prepare(osim,p)
    if kind=='moco_track':
        state_array=model.getStateVariableNames();native_states=[state_array.get(i) for i in range(state_array.getSize())];native_controls=list(osim.createControlNamesFromModel(model))
        if set(native_states)!=set(p['state_bounds']) or set(native_controls)!=set(p['control_bounds']):raise ValueError('Provide complete actual state/control bounds.')
        track=osim.MocoTrack();track.setName('structured_track');track.setModel(processor)
        track.setStatesReference(osim.TableProcessor('reference_states.sto'));track.set_allow_unused_references(False)
        track.set_track_reference_position_derivatives(p['track_reference_derivatives']);track.set_apply_tracked_states_to_guess(True)
        track.set_initial_time(p['initial_time']);track.set_final_time(p['final_time']);track.set_mesh_interval(p['mesh_interval'])
        track.set_states_global_tracking_weight(p['tracking_weight']);track.set_control_effort_weight(p['control_effort_weight'])
        track.set_minimize_control_effort(p['control_effort_weight']>0);track.printToXML('tool.xml')
        study=track.initialize();study.set_write_solution(False);problem=study.updProblem()
        def bound(b,cls):return cls(b[0]) if len(b)==1 else cls(b[0],b[1])
        for name,info in p['state_bounds'].items():
            problem.setStateInfo(name,bound(info['bounds'],osim.MocoBounds),bound(info['initial'],osim.MocoInitialBounds) if 'initial' in info else osim.MocoInitialBounds(),bound(info['final'],osim.MocoFinalBounds) if 'final' in info else osim.MocoFinalBounds())
        for name,info in p['control_bounds'].items():problem.setControlInfo(name,bound(info,osim.MocoBounds))
        solver=osim.MocoCasADiSolver.safeDownCast(study.updSolver());solver.set_parallel(0)
        solver.set_optim_max_iterations(p['max_iterations']);solver.set_optim_convergence_tolerance(p['convergence_tolerance']);solver.set_optim_constraint_tolerance(p['constraint_tolerance'])
        solution=study.solve()
    else:
        import os
        os.environ.setdefault('OPENSIM_MOCO_PARALLEL','0')
        if p['ignore_tendon_compliance']:processor.append(osim.ModOpIgnoreTendonCompliance())
        inverse=osim.MocoInverse();inverse.setName('structured_inverse');inverse.setModel(processor)
        inverse.setKinematics(osim.TableProcessor('reference_states.sto'));inverse.set_kinematics_allow_extra_columns(False)
        inverse.set_initial_time(p['initial_time']);inverse.set_final_time(p['final_time']);inverse.set_mesh_interval(p['mesh_interval'])
        inverse.set_max_iterations(p['max_iterations']);inverse.set_convergence_tolerance(p['convergence_tolerance']);inverse.set_constraint_tolerance(p['constraint_tolerance'])
        inverse.set_minimize_sum_squared_activations(p['minimize_sum_squared_activations']);inverse.printToXML('tool.xml')
        inverse_solution=inverse.solve();solution=inverse_solution.getMocoSolution()
    return finish(osim,solution,p,model,times,names,values,units,kind)
