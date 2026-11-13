"""Original structured RRATool setup; no user setup XML or inferred residuals."""
import json,math,shutil
from pathlib import Path
from xml.etree import ElementTree as ET

def run(osim,p):
    import numpy as np
    model=osim.Model('model.osim');model.finalizeConnections();state=model.initSystem()
    original_centers={model.getBodySet().get(i).getName():[float(model.getBodySet().get(i).getMassCenter().get(j)) for j in range(3)] for i in range(model.getBodySet().getSize())}
    if model.getControllerSet().getSize():raise ValueError('Structured RRA requires a model without preexisting controllers.')
    independent=[model.getCoordinateSet().get(i).getName() for i in range(model.getCoordinateSet().getSize())
        if not model.getCoordinateSet().get(i).getLocked(state) and not model.getCoordinateSet().get(i).isDependent(state)]
    if set(p['task_weights'])!=set(independent) or {d['coordinate'] for d in p['actuators']}!=set(independent):raise ValueError('Every independent unlocked coordinate needs exactly one task and explicit actuator.')
    original=osim.ForceSet(model.getForceSet());original_muscles=model.getMuscles().getSize()
    forces=model.updForceSet()
    for i in range(forces.getSize()-1,-1,-1):
        if osim.Actuator.safeDownCast(forces.get(i)):forces.remove(i)
    for d in p['actuators']:
        coordinate=model.getCoordinateSet().get(d['coordinate']);unit='Nm' if coordinate.getMotionType()==1 else 'N'
        if d['unit']!=unit:raise ValueError('RRA actuator unit does not match coordinate.')
        actuator=osim.CoordinateActuator(d['coordinate']);actuator.setName(d['name']);actuator.setOptimalForce(d['optimal_force'])
        actuator.setMinControl(d['min_control']);actuator.setMaxControl(d['max_control']);model.addForce(actuator)
    model.finalizeConnections();model.initSystem()
    tasks=osim.CMC_TaskSet()
    for name,weight in p['task_weights'].items():
        task=osim.CMC_Joint();task.setName(name);task.setCoordinateName(name);task.setActive(True,False,False)
        task.setWeight(weight);task.setKP(p['kp']);task.setKV(p['kv']);tasks.cloneAndAppend(task)
    tasks.printToXML('rra_tasks.xml')
    controls=osim.ControlSet()
    for d in p['actuators']:
        control=osim.ControlLinear();control.setName(d['name']);control.setIsModelControl(True)
        control.setDefaultParameterMin(d['min_control']);control.setDefaultParameterMax(d['max_control'])
        control.setControlValue(p['start_time'],0.);control.setControlValue(p['end_time'],0.);controls.cloneAndAppend(control)
    controls.printToXML('rra_controls.xml')
    if p['external_forces']:
        document=ET.Element('OpenSimDocument',Version='40000');loads=ET.SubElement(document,'ExternalLoads',name='explicit_loads');objects=ET.SubElement(loads,'objects');ET.SubElement(loads,'groups')
        for d in p['external_forces']:
            force=ET.SubElement(objects,'ExternalForce',name=d['name'])
            for k,v in d.items():
                if k!='name':ET.SubElement(force,k).text=v
        ET.SubElement(loads,'datafile').text='loads.sto';ET.ElementTree(document).write('rra_loads.xml',encoding='utf-8',xml_declaration=True)
    storage=osim.Storage('coordinates.sto');storage.setInDegrees(p['in_degrees'].lower() in {'yes','true'});storage.printToFile('rra_reference.sto','w')
    tool=osim.RRATool();tool.setName('rra');tool.setModel(model);tool.setOriginalForceSet(original);tool.setReplaceForceSet(False)
    tool.setDesiredKinematicsFileName('rra_reference.sto');tool.setTaskSetFileName('rra_tasks.xml');tool.setControlsFileName('rra_controls.xml')
    tool.setInitialTime(p['start_time']);tool.setFinalTime(p['end_time']);tool.setResultsDir('.')
    tool.setLowpassCutoffFrequency(p['lowpass_cutoff_hz']);tool.setAdjustCOMToReduceResiduals(bool(p['adjust_com_body']))
    if p['adjust_com_body']:tool.setAdjustedCOMBody(p['adjust_com_body'])
    if p['external_forces']:tool.setExternalLoadsFileName('rra_loads.xml')
    tool.setOutputModelFileName('adjusted_model.osim');tool.setMaxDT(.01);tool.setMinDT(1e-8);tool.setErrorTolerance(1e-5);tool.setMaximumNumberOfSteps(200000)
    tool.printToXML('rra_setup.xml')
    if not tool.run():raise RuntimeError('RRATool returned false; inspect generated settings/native log.')
    if not Path('adjusted_model.osim').is_file():
        if p['adjust_com_body']:raise ValueError('RRA did not publish its requested COM-adjusted model.')
        # With COM adjustment disabled RRA changes only kinematics. The Python
        # wrapper does not expose writeAdjustedModel; retain the original model.
        original_model=osim.Model('model.osim');original_model.printToXML('adjusted_model.osim')
    adjusted=osim.Model('adjusted_model.osim');adjusted.initSystem()
    if adjusted.getMuscles().getSize()!=original_muscles:raise ValueError('Saved RRA model failed to restore original muscle set.')
    source=next(Path('.').glob('rra_Kinematics_q.sto'));shutil.copyfile(source,'rra_coordinates.mot')
    force_files=list(Path('.').glob('*Actuation_force.sto'))
    if len(force_files)!=1:raise ValueError('Expected exactly one RRA actuation force table.')
    shutil.copyfile(force_files[0],'rra_forces.sto')
    from native_tables import strict_native_times
    time_normalization=[strict_native_times(name) for name in ('rra_coordinates.mot','rra_forces.sto')]
    reference=osim.TimeSeriesTable('rra_reference.sto');actual=osim.TimeSeriesTable('rra_coordinates.mot')
    t=np.asarray(actual.getIndependentColumn(),dtype=float);rt=np.asarray(reference.getIndependentColumn(),dtype=float)
    if len(t)<2 or t[0]>p['start_time']+.001001 or t[-1]<p['end_time']-.001001:raise ValueError('RRA output window differs beyond its 1 ms controller initialization: '+str([float(t[0]),float(t[-1])]))
    ref_degrees=p['in_degrees'].lower() in {'yes','true'}
    text=Path('rra_coordinates.mot').read_text(encoding='utf-8-sig');act_degrees='indegrees=yes' in text.lower().replace(' ','')
    fit={}
    for name in independent:
        coordinate=adjusted.getCoordinateSet().get(name);rotational=coordinate.getMotionType()==1
        reference_values=np.array([reference.getDependentColumn(name)[i] for i in range(len(rt))],dtype=float)
        values=np.array([actual.getDependentColumn(name)[i] for i in range(len(t))],dtype=float)
        if rotational and ref_degrees:reference_values=np.deg2rad(reference_values)
        if rotational and act_degrees:values=np.deg2rad(values)
        errors=values-np.interp(t,rt,reference_values)
        if not np.isfinite(errors).all():raise ValueError('Nonfinite RRA tracking error.')
        fit[name]={'rms':float(np.sqrt(np.mean(errors**2))),'max_abs':float(np.max(np.abs(errors))),'unit':'rad' if rotational else 'm'}
        if name in p['max_tracking_error'] and fit[name]['max_abs']>p['max_tracking_error'][name]:raise ValueError('RRA tracking exceeds caller limit: '+name)
    quality=dict(native_completed=True,coordinate_fit=fit,original_muscles_restored=original_muscles,com_adjustment_body=p['adjust_com_body'],
        recommended_mass_changes_applied=False,rows=len(t),no_claim_of_residual_reduction=True,native_time_normalization=time_normalization,
        requested_time_range_s=[p['start_time'],p['end_time']],time_range_s=[float(t[0]),float(t[-1])],
        boundary_time_note='Native CMC may omit up to 1 ms at a boundary; comparison uses the actual common interval.')
    quality['body_com_change_m']={name:[float(adjusted.getBodySet().get(name).getMassCenter().get(j))-values[j] for j in range(3)] for name,values in original_centers.items()}
    adjusted.printToXML('model.osim');Path('rra_quality.json').write_text(json.dumps(quality,indent=2,allow_nan=False),encoding='utf-8')
    outputs=['model.osim','rra_coordinates.mot','rra_forces.sto','rra_tasks.xml','rra_controls.xml','rra_setup.xml','rra_quality.json']
    if Path('rra_loads.xml').is_file():outputs.append('rra_loads.xml')
    return dict(outputs=outputs,quality=quality,opensim_version=osim.GetVersionAndDate(),scope='Native RRATool with explicit torque/residual profile; original actuators restored. Review ID comparison and coordinate errors before adopting adjusted model/kinematics.')
