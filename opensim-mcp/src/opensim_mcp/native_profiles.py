"""Native calibration and explicit actuator profiles. CPython 3.8+, generated requests only."""
import json
import math
from pathlib import Path


def vector(v): return [float(v.get(i)) for i in range(3)]


def place_markers(osim,p):
    model=osim.Model('model.osim');model.finalizeConnections();state=model.initSystem()
    marker_set=model.updMarkerSet();names=[marker_set.get(i).getName() for i in range(marker_set.getSize())]
    if set(p['movable_markers'])-set(names) or set(p['marker_weights'])-set(names): raise ValueError('Unknown model marker.')
    trc=osim.TimeSeriesTableVec3('static.trc');labels=list(trc.getColumnLabels())
    if set(p['marker_weights'])-set(labels) or set(p['movable_markers'])-set(labels): raise ValueError('Selected marker absent from static trial.')
    before={name:vector(marker_set.get(name).get_location()) for name in names}
    fixed={name:marker_set.get(name).get_fixed() for name in names}
    for name in names: marker_set.get(name).set_fixed(name not in p['movable_markers'])
    placer=osim.MarkerPlacer();placer.setApply(True);placer.setMoveModelMarkers(True)
    placer.setMarkerFileName('static.trc');times=osim.ArrayDouble();times.append(p['start_time']);times.append(p['end_time']);placer.setTimeRange(times)
    placer.setMaxMarkerMovement(p['max_static_motion_m'])
    placer.setOutputModelFileName('placed.osim');placer.setOutputMarkerFileName('placed_markers.xml');placer.setOutputMotionFileName('static_pose.mot')
    tasks=placer.getIKTaskSet()
    for name,weight in p['marker_weights'].items():
        task=osim.IKMarkerTask();task.setName(name);task.setWeight(weight);task.setApply(True);tasks.cloneAndAppend(task)
    for name,info in p['coordinate_targets'].items():
        model.getCoordinateSet().get(name)
        task=osim.IKCoordinateTask();task.setName(name);task.setWeight(info['weight']);task.setApply(True)
        task.setValueType(osim.IKCoordinateTask.ManualValue);task.setValue(info['value']);tasks.cloneAndAppend(task)
    placer.printToXML('marker_placement.xml')
    if not placer.processModel(model,''): raise RuntimeError('Native MarkerPlacer returned false.')
    shifts={name:math.sqrt(sum((a-b)**2 for a,b in zip(vector(model.getMarkerSet().get(name).get_location()),before[name]))) for name in names}
    maximum=max(shifts.values())
    if maximum>p['max_marker_movement_m']: raise ValueError('Marker offset exceeds caller movement limit: '+str(maximum))
    if any(shifts[n]>1e-10 for n in names if n not in p['movable_markers']): raise ValueError('A protected marker moved.')
    # Restore original semantic fixed flags after the scoped placement operation.
    for name in names: model.updMarkerSet().get(name).set_fixed(fixed[name])
    model.printToXML('model.osim');reopened=osim.Model('model.osim');reopened.initSystem()
    return {'outputs':['model.osim','placed_markers.xml','static_pose.mot','marker_placement.xml'],
        'quality':{'max_marker_shift_m':maximum,'marker_shifts_m':shifts,'protected_markers_unchanged':True,'native_reopened':True},
        'opensim_version':osim.GetVersionAndDate(),
        'scope':'Native static MarkerPlacer on an already scaled model; explicit movable markers and IK weights. Static pose output is one frame. Movement limit is separate from marker-fit validity.'}


def configure_actuators(osim,p):
    model=osim.Model('model.osim');model.finalizeConnections();state=model.initSystem()
    coordinates=model.getCoordinateSet();forces=model.getForceSet();existing=set(forces.get(i).getName() for i in range(forces.getSize()))
    added=[];assigned=set()
    for i in range(forces.getSize()):
        old=osim.CoordinateActuator.safeDownCast(forces.get(i))
        if old:
            coordinate=old.getCoordinate()
            if coordinate is None:raise ValueError('Existing CoordinateActuator is not connected.')
            assigned.add(coordinate.getAbsolutePathString())
    for d in p['definitions']:
        if d['name'] in existing: raise ValueError('Actuator name already exists.')
        coordinate=coordinates.get(d['coordinate']);motion=coordinate.getMotionType();unit='Nm' if motion==1 else ('N' if motion==2 else None)
        if unit is None or unit!=d['unit']: raise ValueError('Actuator unit does not match native coordinate motion type.')
        if coordinate.getDefaultLocked() or coordinate.isDependent(state): raise ValueError('Locked/dependent coordinate cannot receive this profile actuator.')
        if coordinate.getAbsolutePathString() in assigned:raise ValueError('Coordinate already has a CoordinateActuator.')
        actuator=osim.CoordinateActuator(coordinate.getName());actuator.setName(d['name']);actuator.setOptimalForce(d['optimal_force'])
        actuator.setMinControl(d['min_control']);actuator.setMaxControl(d['max_control']);model.addForce(actuator)
        assigned.add(coordinate.getAbsolutePathString())
        added.append(dict(d,coordinate_path=coordinate.getAbsolutePathString()))
    model.finalizeConnections();model.initSystem();model.printToXML('model.osim')
    check=osim.Model('model.osim');check.initSystem()
    for d in added:
        actuator=osim.CoordinateActuator.safeDownCast(check.getForceSet().get(d['name']))
        if not actuator or abs(actuator.getOptimalForce()-d['optimal_force'])>1e-10: raise ValueError('Actuator readback failed.')
    Path('actuator_profile.json').write_text(json.dumps({'actuators':added}),encoding='utf-8')
    return {'outputs':['model.osim','actuator_profile.json'],'actuators':added,'opensim_version':osim.GetVersionAndDate(),
        'quality':{'added_actuators':len(added),'native_reopened':True},
        'scope':'Explicit coordinate actuators only. No automatic reserves, residual classification or contact forces. Role metadata does not alter OpenSim actuator physics.'}


def actuator_usage(osim,p):
    model=osim.Model('model.osim');model.initSystem();table=osim.TimeSeriesTable('forces.sto')
    reference=osim.TimeSeriesTable('reference.sto') if p['has_reference'] else None
    times=list(table.getIndependentColumn());ref_times=list(reference.getIndependentColumn()) if reference else None
    if reference and (len(times)!=len(ref_times) or any(abs(a-b)>1e-6 for a,b in zip(times,ref_times))): raise ValueError('Usage/reference samples must coincide; no implicit interpolation.')
    metrics={};ratios=[]
    for d in p['definitions']:
        actuator=osim.CoordinateActuator.safeDownCast(model.getForceSet().get(d['name']))
        if not actuator: raise ValueError('Usage assessment currently supports explicit CoordinateActuators.')
        motion=actuator.getCoordinate().getMotionType();unit='Nm' if motion==1 else ('N' if motion==2 else None)
        if unit!=d['unit']: raise ValueError('Usage unit differs from native actuator force/moment unit.')
        column=table.getDependentColumn(d['force_column']);values=[float(column[i]) for i in range(table.getNumRows())]
        if not values or not all(math.isfinite(v) for v in values): raise ValueError('Nonfinite actuator forces.')
        rms=math.sqrt(sum(v*v for v in values)/len(values));peak=max(abs(v) for v in values)
        item={'role':d['role'],'unit':unit,'rms':rms,'peak_abs':peak,'rms_fraction_reference':None}
        if reference:
            column=reference.getDependentColumn(d['reference_column']);values=[float(column[i]) for i in range(reference.getNumRows())]
            denominator=math.sqrt(sum(v*v for v in values)/len(values))
            if denominator>1e-12: item['rms_fraction_reference']=rms/denominator;ratios.append(rms/denominator)
        metrics[d['name']]=item
    quality={'actuators':metrics,'max_rms_fraction_reference':max(ratios) if ratios and len(ratios)==len(metrics) else None,
             'rows':len(times)}
    Path('actuator_usage.json').write_text(json.dumps(quality,allow_nan=False),encoding='utf-8')
    return {'outputs':['actuator_usage.json'],'quality':quality,'opensim_version':osim.GetVersionAndDate(),
        'scope':'RMS generalized actuator force/moment divided by explicitly paired ID/reference column RMS. Near-zero denominator is not assessed. No physiological acceptance inferred.'}


def run(osim,kind,parameters):
    return {'marker_placement':place_markers,'configure_actuators':configure_actuators,'actuator_usage':actuator_usage}[kind](osim,parameters)
