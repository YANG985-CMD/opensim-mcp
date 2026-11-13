"""Native node-level constraints, actuator outputs and state/control bounds."""
import json,math
from pathlib import Path

def run(osim,p):
    import numpy as np
    from native_tracking import prepare
    # Reuse the same explicit external-load construction as the Moco profile.
    model,processor,_,_,_,_=prepare(osim,p)
    if p['ignore_tendon_compliance']:processor.append(osim.ModOpIgnoreTendonCompliance())
    model=processor.process();state=model.initSystem()
    states=osim.TimeSeriesTable('states.sto');controls=osim.TimeSeriesTable('controls.sto')
    st=np.asarray(states.getIndependentColumn(),dtype=float);ct=np.asarray(controls.getIndependentColumn(),dtype=float)
    if len(st)!=len(ct) or not np.allclose(st,ct,rtol=0,atol=1e-9):raise ValueError('States/controls must share every audit node.')
    native=model.getStateVariableNames();names=[native.get(i) for i in range(native.getSize())]
    if set(states.getColumnLabels())!=set(names):raise ValueError('Audit requires every actual native state, no omitted/extra variables.')
    mapping=osim.StdVectorInt();control_names=list(osim.createControlNamesFromModel(model,mapping))
    if set(controls.getColumnLabels())!=set(control_names):raise ValueError('Audit requires every actual control.')
    state_values={n:np.asarray([states.getDependentColumn(n)[i] for i in range(len(st))],dtype=float) for n in names}
    control_values={n:np.asarray([controls.getDependentColumn(n)[i] for i in range(len(ct))],dtype=float) for n in control_names}
    samples={};activations={};qerr=[];uerr=[];control_violation=[]
    actuators=model.getActuators()
    for k,t in enumerate(st):
        state.setTime(float(t))
        values=osim.Vector(len(names),0.)
        for i,n in enumerate(names):values.set(i,float(state_values[n][k]))
        model.setStateVariableValues(state,values)
        inputs=osim.Vector(model.getNumControls(),0.)
        for i,n in enumerate(control_names):inputs.set(mapping[i],float(control_values[n][k]))
        model.realizeVelocity(state);model.setControls(state,inputs)
        qe=state.getQErr();ue=state.getUErr();qerr.append(max([abs(float(qe.get(i))) for i in range(qe.size())] or [0.]))
        uerr.append(max([abs(float(ue.get(i))) for i in range(ue.size())] or [0.]))
        model.realizeDynamics(state)
        for i in range(actuators.getSize()):
            scalar=osim.ScalarActuator.safeDownCast(actuators.get(i))
            if scalar is None:continue
            name=scalar.getAbsolutePathString();samples.setdefault(name,[]).append(float(scalar.getActuation(state)))
            value=float(scalar.getControl(state));control_violation.append(max(0.,scalar.getMinControl()-value,value-scalar.getMaxControl()))
    def metrics(values):
        a=np.asarray(values,dtype=float)
        if not np.isfinite(a).all():raise ValueError('Nonfinite native audit quantity.')
        return dict(rms=float(np.sqrt(np.mean(a*a))),peak_abs=float(np.max(np.abs(a))),minimum=float(np.min(a)),maximum=float(np.max(a)))
    forces={}
    for name,values in samples.items():
        component=model.getComponent(name);coordinate=osim.CoordinateActuator.safeDownCast(component);muscle=osim.Muscle.safeDownCast(component)
        unit='N' if muscle else ('Nm' if coordinate.getCoordinate().getMotionType()==1 else 'N') if coordinate else 'native actuator units'
        forces[name]=dict(metrics(values),unit=unit,component_class=component.getConcreteClassName())
    activation={name:dict(metrics(values),unit='dimensionless',max_bound_violation=max(0.,float(-np.min(values)),float(np.max(values)-1.))) for name,values in state_values.items() if name.endswith('/activation')}
    result=dict(nodes=len(st),time_range_s=[float(st[0]),float(st[-1])],state_count=len(names),control_count=len(control_names),
        max_position_constraint_error=max(qerr),max_velocity_constraint_error=max(uerr),max_native_control_bound_violation=max(control_violation or [0.]),
        actuator_output=forces,muscle_activation=activation,
        scope='Every exported node evaluated with explicit native states, controls and loads. Constraint vector components retain native mixed units. Not between-node collocation error, a forward replay, individual contact pressure or physiological acceptance.')
    Path('trajectory_audit.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    force_names=sorted(samples);header='Native actuator outputs\nversion=1\nnRows='+str(len(st))+'\nnColumns='+str(len(force_names)+1)+'\ninDegrees=no\nendheader\ntime\t'+'\t'.join(force_names)+'\n'
    Path('actuator_outputs.sto').write_text(header+'\n'.join('\t'.join(format(float(v),'.17g') for v in [st[k]]+[samples[n][k] for n in force_names]) for k in range(len(st)))+'\n',encoding='utf-8')
    return dict(outputs=['trajectory_audit.json','actuator_outputs.sto'],quality=result,opensim_version=osim.GetVersionAndDate())
