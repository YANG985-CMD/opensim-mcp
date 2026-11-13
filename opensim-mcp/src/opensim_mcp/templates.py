"""Generate a reviewable full muscle-analysis project without inferring physics."""
from .core import InputError,MAX_MODEL,bounded_read,trc_info,xml_model
from .projects import create_project

def create_biomechanics_project(cfg,name,model_path,static_marker_path,movement_marker_path,subject_mass_kg,body_scales,
        movable_markers,marker_weights,lowpass_cutoff_hz,loads_path=None,external_forces=None,no_external_loads=False,
        reserve_definitions=None,rra_settings=None,quality_limits=None,residual_force_columns=None,max_marker_movement_m=.02,max_static_motion_m=.01):
    _,model=xml_model(bounded_read(cfg.input_path(model_path,'.osim'),MAX_MODEL))
    if not any('Muscle' in element.tag for element in model.iter()):raise InputError('The full muscle project requires muscles; use a basic project for an unactuated model.')
    markers={e.get('name') for e in model.iter('Marker')}
    if set(movable_markers)-markers or set(marker_weights)-markers:raise InputError('Marker placement/IK weights reference unknown model markers.')
    static=trc_info(bounded_read(cfg.input_path(static_marker_path,'.trc'),64*1024**2));moving=trc_info(bounded_read(cfg.input_path(movement_marker_path,'.trc'),64*1024**2))
    if type(no_external_loads) is not bool or bool(loads_path)==no_external_loads:raise InputError('Choose explicit loads or no_external_loads=true.')
    inputs={'model':dict(path=model_path,kind='model'),'static':dict(path=static_marker_path,kind='markers',length_unit=static['units']),
            'movement':dict(path=movement_marker_path,kind='markers',length_unit=moving['units'])}
    load_parameters={'no_external_loads':no_external_loads}
    if loads_path:
        inputs['loads']=dict(path=loads_path,kind='loads',force_unit='N',point_unit='m',torque_unit='Nm')
        load_parameters.update(loads_path='${inputs.loads}',external_forces=external_forces)
    elif external_forces:raise InputError('External forces supplied without loads.')
    stages=[dict(id='scale',workflow='scale',parameters=dict(model_path='${inputs.model}',subject_mass_kg=subject_mass_kg,body_scales=body_scales)),
        dict(id='placement',workflow='marker_placement',parameters=dict(model_path='${stages.scale.model}',static_marker_path='${inputs.static}',movable_markers=movable_markers,marker_weights=marker_weights,max_marker_movement_m=max_marker_movement_m,max_static_motion_m=max_static_motion_m)),
        dict(id='ik',workflow='ik',parameters=dict(model_path='${stages.placement.model}',marker_path='${inputs.movement}',marker_weights=marker_weights)),
        dict(id='fit',workflow='ik_quality',parameters=dict(model_path='${stages.placement.model}',coordinates_path='${stages.ik.motion}',marker_path='${inputs.movement}',interpolation='linear'))]
    model_ref='${stages.placement.model}';motion_ref='${stages.ik.motion}'
    if rra_settings:
        if not isinstance(rra_settings,dict) or set(rra_settings)-{'actuators','task_weights','adjust_com_body','kp','kv','max_tracking_error'}:raise InputError('Unsupported RRA project settings.')
        stages.append(dict(id='rra',workflow='rra',parameters=dict(model_path=model_ref,coordinates_path=motion_ref,lowpass_cutoff_hz=lowpass_cutoff_hz,**load_parameters,**rra_settings)))
        model_ref='${stages.rra.model}';motion_ref='${stages.rra.motion}'
    if reserve_definitions:
        stages.append(dict(id='reserves',workflow='configure_actuators',parameters=dict(model_path=model_ref,definitions=reserve_definitions)));model_ref='${stages.reserves.model}'
    common=dict(model_path=model_ref,coordinates_path=motion_ref,lowpass_cutoff_hz=lowpass_cutoff_hz,**load_parameters)
    stages.extend([dict(id='id',workflow='id',parameters=common),dict(id='muscles',workflow='muscle_analysis',parameters=dict(model_path=model_ref,coordinates_path=motion_ref,lowpass_cutoff_hz=lowpass_cutoff_hz)),
        dict(id='so',workflow='static_optimization',parameters=common),dict(id='reactions',workflow='joint_reaction',parameters=dict(common,forces_path='${stages.so.forces}'))])
    quality_limits=quality_limits or {};allowed={'marker_rms_m','residual_force_rms_fraction_BW'}
    if not isinstance(quality_limits,dict) or set(quality_limits)-allowed:raise InputError('Unknown project quality threshold.')
    checks=[];residuals=[]
    for metric,limit in quality_limits.items():
        if metric=='marker_rms_m':checks.append(dict(id='marker_fit',stage='fit',metric=metric,limit=limit,unit='m'))
        else:
            if not residual_force_columns or len(residual_force_columns)!=3:raise InputError('Residual BW threshold requires three explicitly named force columns.')
            residuals.append(dict(stage='id',force_columns=residual_force_columns));checks.append(dict(id='residual_force',stage='id',metric=metric,limit=limit,unit='BW fraction'))
    project=dict(schema_version=1,name=name,inputs=inputs,stages=stages,checks=checks,residuals=residuals,
        description='Explicit scale/placement/IK/ID/muscle/SO/JointReaction project. Optional RRA and reserve profile. Review every input, assumption and threshold before execution.')
    result=create_project(cfg,project);result.update(generated_workflows=[s['workflow'] for s in stages],ready_for_review=True,
        quality_thresholds_automatically_inferred=False);return result
