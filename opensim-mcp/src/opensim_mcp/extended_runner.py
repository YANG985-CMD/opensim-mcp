"""Generated structured requests only; loaded by the isolated native interpreter.

No MCP dependency. Compatible with CPython 3.8 for legacy scaling.
"""
import math
from pathlib import Path
import statistics


def scale(osim,p,static_trc=None):
    model=osim.Model('model.osim');model.finalizeConnections();state=model.initSystem()
    model.assemble(state);model.realizePosition(state)
    bodies=model.getBodySet();names=[bodies.get(i).getName() for i in range(bodies.getSize())]
    factors=dict((name,list(value)) for name,value in p['body_scales'].items())
    if set(factors)-set(names):raise ValueError('Unknown scaling bodies: '+str(set(factors)-set(names)))
    measured=[];assigned=set()
    if static_trc:
        lines=Path(static_trc).read_text(encoding='utf-8-sig').splitlines()
        labels=lines[3].split('\t')[2:];marker_names=[v.strip() for i,v in enumerate(labels) if i%3==0]
        rows=[[float(x) for x in line.split()] for line in lines[6:] if line.strip()]
        unit=lines[2].split()[4].lower();unit_scale=.001 if unit=='mm' else 1.
        for item in p['measurements']:
            body=item['body']
            if body not in names or body in p['body_scales']:raise ValueError('Unknown body or overlapping manual/measurement scaling.')
            ratios=[]
            for a,b in item['marker_pairs']:
                ma=model.getMarkerSet().get(a).getLocationInGround(state)
                mb=model.getMarkerSet().get(b).getLocationInGround(state)
                reference=math.sqrt(sum((ma.get(i)-mb.get(i))**2 for i in range(3)))
                if reference<1e-6:raise ValueError('Reference marker pair is too short.')
                ia=2+3*marker_names.index(a);ib=2+3*marker_names.index(b)
                distances=[math.sqrt(sum((row[ia+i]-row[ib+i])**2 for i in range(3)))*unit_scale for row in rows]
                average=statistics.mean(distances);ratio=average/reference
                if not .2<=ratio<=5:raise ValueError('Measured scale factor is outside [0.2,5].')
                ratios.append(ratio)
                measured.append({'body':body,'pair':[a,b],'reference_distance_m':reference,'experimental_distance_m':average,
                                 'experimental_cv':statistics.pstdev(distances)/average if average else None})
            factor=statistics.mean(ratios);factors.setdefault(body,[1.,1.,1.])
            for axis in item['axes']:
                key=(body,axis)
                if key in assigned:raise ValueError('Overlapping measurement axes.')
                assigned.add(key);factors[body]['xyz'.index(axis)]=factor
    scale_set=osim.ScaleSet()
    for name,values in factors.items():
        entry=osim.Scale();entry.setSegmentName(name);entry.setScaleFactors(osim.Vec3(*values));entry.setApply(True)
        scale_set.cloneAndAppend(entry)
    original_mass=model.getTotalMass(state)
    if not model.scale(state,scale_set,p['preserve_mass_distribution'],p['subject_mass_kg']):raise RuntimeError('OpenSim Model.scale returned false.')
    model.finalizeConnections();state=model.initSystem();model.assemble(state);model.realizePosition(state)
    mass=model.getTotalMass(state)
    if abs(mass-p['subject_mass_kg'])>1e-6*max(1,p['subject_mass_kg']):raise ValueError('Scaled total mass does not match requested subject mass.')
    for item in measured:
        a,b=item['pair'];ma=model.getMarkerSet().get(a).getLocationInGround(state);mb=model.getMarkerSet().get(b).getLocationInGround(state)
        actual=math.sqrt(sum((ma.get(i)-mb.get(i))**2 for i in range(3)))
        item['scaled_distance_m']=actual;item['error_m']=actual-item['experimental_distance_m']
    maximum=max([abs(m['error_m']) for m in measured] or [0.])
    if p['max_measurement_error_m'] is not None and maximum>p['max_measurement_error_m']:raise ValueError('Scaled measurement error exceeds caller threshold.')
    model.printToXML('scaled.osim');scale_set.printToXML('scale_factors.xml')
    reopened=osim.Model('scaled.osim');reopened.initSystem()
    return {'outputs':['scaled.osim','scale_factors.xml'],'opensim_version':osim.GetVersionAndDate(),
            'quality':{'original_mass_kg':original_mass,'scaled_mass_kg':mass,'mass_error_kg':mass-p['subject_mass_kg'],
                       'measurements':measured,'max_pair_distance_error_m':maximum if measured else None,
                       'native_initialized_and_reopened':True},'body_scales':factors,
            'unscaled_bodies':[n for n in names if n not in factors],
            'scope':'Native model scaling; virtual marker relocation/MarkerPlacer is not performed.'}


def moco(osim,p):
    import numpy as np
    if not hasattr(osim,'MocoStudy') or not hasattr(osim,'MocoCasADiSolver'):raise RuntimeError('This API build has no Moco/CasADi support.')
    model=osim.Model('model.osim');model.finalizeConnections();model.initSystem()
    state_names=model.getStateVariableNames()
    states=[state_names.get(i) for i in range(state_names.getSize())]
    controls=list(osim.createControlNamesFromModel(model))
    if set(states)!=set(p['state_bounds']):raise ValueError('state_bounds must explicitly cover every model state: '+str(states))
    if set(controls)!=set(p['control_bounds']):raise ValueError('control_bounds must explicitly cover every model control: '+str(controls))
    study=osim.MocoStudy();study.setName('structured_moco');study.set_write_solution(False)
    problem=study.updProblem();problem.setModel(model)
    problem.setTimeBounds(osim.MocoInitialBounds(p['initial_time']),osim.MocoFinalBounds(p['final_time']))
    def bound(values,kind):
        return kind(values[0]) if len(values)==1 else kind(values[0],values[1])
    for name,info in p['state_bounds'].items():
        general=bound(info['bounds'],osim.MocoBounds)
        initial=bound(info['initial'],osim.MocoInitialBounds) if 'initial' in info else osim.MocoInitialBounds()
        final=bound(info['final'],osim.MocoFinalBounds) if 'final' in info else osim.MocoFinalBounds()
        problem.setStateInfo(name,general,initial,final)
    for name,info in p['control_bounds'].items():problem.setControlInfo(name,bound(info,osim.MocoBounds))
    goal=osim.MocoControlGoal('control_effort',p['control_effort_weight']);problem.addGoal(goal)
    solver=study.initCasADiSolver();solver.set_num_mesh_intervals(p['mesh_intervals'])
    solver.set_optim_max_iterations(p['max_iterations']);solver.set_optim_convergence_tolerance(p['convergence_tolerance'])
    solver.set_optim_constraint_tolerance(p['constraint_tolerance']);solver.set_parallel(0)
    study.printToXML('study.omoco')
    solution=study.solve()
    if not solution.success():raise RuntimeError('Moco failed: '+solution.getStatus())
    objective=solution.getObjective()
    if not math.isfinite(objective):raise ValueError('Moco objective is nonfinite.')
    refinement=None
    if p['refine_mesh']:
        solver.set_num_mesh_intervals(p['mesh_intervals']*2);solver.setGuess(solution)
        refined=study.solve()
        if not refined.success():raise RuntimeError('Refined Moco solve failed: '+refined.getStatus())
        denominator=max(abs(refined.getObjective()),abs(objective))
        relative=abs(refined.getObjective()-objective)/denominator if denominator else 0.
        refinement={'coarse_objective':objective,'refined_objective':refined.getObjective(),
                    'relative_objective_change':relative,'refined_intervals':p['mesh_intervals']*2}
        if not math.isfinite(relative) or relative>p['max_mesh_objective_relative_change']:raise ValueError('Moco mesh objective change exceeds caller threshold.')
        solution=refined;objective=solution.getObjective();study.printToXML('study.omoco')
    times=np.asarray(solution.getTimeMat()).reshape(-1)
    values=np.asarray(solution.getStatesTrajectoryMat());control=np.asarray(solution.getControlsTrajectoryMat())
    if not np.isfinite(values).all() or not np.isfinite(control).all() or not np.isfinite(times).all():raise ValueError('Nonfinite Moco trajectory.')
    if len(times)<2 or not np.all(np.diff(times)>0) or abs(times[0]-p['initial_time'])>1e-7 or abs(times[-1]-p['final_time'])>1e-7:
        raise ValueError('Moco time coverage is invalid.')
    violation=0.;endpoint_error=0.
    for names,matrix,infos in ((list(solution.getStateNames()),values,p['state_bounds']),
                                (list(solution.getControlNames()),control,p['control_bounds'])):
        for i,name in enumerate(names):
            info=infos[name];limits=info['bounds'] if isinstance(info,dict) else info
            violation=max(violation,float(np.max(np.maximum(limits[0]-matrix[:,i],matrix[:,i]-limits[-1]))),0.)
            if isinstance(info,dict):
                for row,key in ((0,'initial'),(-1,'final')):
                    if key in info:
                        b=info[key];endpoint_error=max(endpoint_error,b[0]-float(matrix[row,i]),float(matrix[row,i])-b[-1],0.)
    tolerance=max(1e-7,p['constraint_tolerance']*10)
    if max(violation,endpoint_error)>tolerance:raise ValueError('Moco trajectory bounds/endpoint error exceeds tolerance.')
    solution.write('solution.sto')
    osim.STOFileAdapter.write(solution.exportToStatesTable(),'states.sto')
    osim.STOFileAdapter.write(solution.exportToControlsTable(),'controls.sto')
    return {'outputs':['solution.sto','states.sto','controls.sto','study.omoco'],
            'opensim_version':osim.GetVersionAndDate(),'quality':{'solver_success':True,'solver_status':solution.getStatus(),
              'iterations':solution.getNumIterations(),'objective':objective,'max_bound_violation':violation,
              'max_endpoint_bound_violation':endpoint_error,'checked_tolerance':tolerance,
              'mesh_refinement':refinement,'rows':len(times)},
            'scope':'Fixed-time Moco optimal control with explicit complete state/control bounds and control-effort goal. Solver feasibility is reported; physiological validity is not inferred.'}


def run(osim,request):
    if request['kind']=='trajectory_audit':
        from native_trajectory_audit import run as audit
        return audit(osim,request['parameters'])
    if request['kind']=='wearable_assembly':
        from native_wearable import run as wearable
        return wearable(osim,request['parameters'])
    if request['kind']=='muscle_metadata':
        from native_muscle import metadata
        return metadata(osim,request['parameters'])
    if request['kind']=='animation_frames':
        from native_animation import run as animation
        return animation(osim,request['parameters'])
    if request['kind']=='topology_preview':
        from native_topology import run as topology
        return topology(osim,request['parameters'])
    if request['kind']=='prepare_moco_model':
        from native_moco_model import run as prepare
        return prepare(osim,request['parameters'])
    if request['kind']=='study_edit':
        from worker import Runtime
        runtime=Runtime(osim);runtime.dispatch('load',dict(staged_path='model.osim',source_path='model.osim'))
        for edit in request['parameters']['edits']:runtime.change(edit)
        runtime.dispatch('save',dict(destination='model.osim'))
        return dict(outputs=['model.osim'],quality={'native_initialized':True},opensim_version=osim.GetVersionAndDate())
    if request['kind']=='rra':
        from native_rra import run as rra
        return rra(osim,request['parameters'])
    if request['kind'] in {'moco_track','moco_inverse'}:
        from native_tracking import run as tracking
        return tracking(osim,request['kind'],request['parameters'])
    if request['kind'] in {'marker_placement','configure_actuators','actuator_usage'}:
        from native_profiles import run as profile
        return profile(osim,request['kind'],request['parameters'])
    if request['kind']=='scale':return scale(osim,request['parameters'],request.get('static_trc'))
    if request['kind']=='moco':return moco(osim,request['parameters'])
    if request['kind']=='ik_quality':
        import json
        p=request['parameters'];model=osim.Model('model.osim');state=model.initSystem()
        sums=dict((n,[]) for n in p['markers'])
        for frame in p['frames']:
            for name,value in frame['coordinates'].items():
                coordinate=model.getCoordinateSet().get(name)
                if p['in_degrees'].lower() in {'yes','true'} and coordinate.getMotionType()==1:value=math.radians(value)
                coordinate.setValue(state,value,False)
            state.setTime(frame['time']);model.assemble(state);model.realizePosition(state)
            for name,experimental in frame['markers'].items():
                actual=model.getMarkerSet().get(name).getLocationInGround(state)
                sums[name].append(sum((actual.get(i)-experimental[i])**2 for i in range(3)))
        all_errors=[v for series in sums.values() for v in series]
        rms=math.sqrt(sum(all_errors)/len(all_errors))
        quality={'marker_rms_m':rms,'marker_max_error_m':math.sqrt(max(all_errors)),
                 'per_marker':dict((n,{'rms_m':math.sqrt(sum(v)/len(v)),'max_error_m':math.sqrt(max(v))}) for n,v in sums.items()),
                 'checked_frames':len(p['frames']),'source_coordinate_rows':p['source_coordinate_rows'],
                 'max_time_match_error_s':p['max_time_match_error_s'],'time_match_tolerance_s':p['time_match_tolerance_s'],
                 'interpolation':p['interpolation'],'interpolated_frames':p['interpolated_frames'],
                 'rms_threshold_m':p['rms_threshold_m'],'threshold_passed':rms<=p['rms_threshold_m'] if p['rms_threshold_m'] is not None else None}
        Path('ik_quality.json').write_text(json.dumps(quality),encoding='utf-8')
        return {'outputs':['ik_quality.json'],'quality':quality,'opensim_version':osim.GetVersionAndDate(),
                'scope':'Independent native marker-position residuals; marker interpolation only when explicitly requested. Not anatomical/physiological validation.'}
    raise ValueError('Unsupported structured native request.')
