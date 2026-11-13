"""Structured data, study and recovery tools added after v0.8."""
from typing import Any
from mcp.types import ToolAnnotations

def register_v1(mcp,cfg,api,gui,push_gui,checkpoints,transactions):
    read=ToolAnnotations(readOnlyHint=True,openWorldHint=False)
    write=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)
    @mcp.tool(annotations=write,structured_output=True)
    def export_model_animation(motion_path:str,geometry_model_path:str|None=None,geometry_roots:list[str]|None=None,
                               comparison_motion_path:str|None=None,marker_path:str|None=None,max_frames:int=200,
                               mesh_scale_factor:float=1.,error_color_range_m:float=.03,angles_in_degrees:bool|None=None,
                               muscle_result_path:str|None=None,comparison_muscle_result_path:str|None=None,muscle_volume_path:str|None=None,
                               muscle_data_interpolation:str='none')->dict[str,Any]:
        """Offline interactive 3D player: surfaces, native muscle paths with visibility/width controls, timeline, orbit/zoom, joint curves, comparison motion and marker-distance coloring. Native transforms and active/wrapped muscle paths are sampled on a model copy. Optional muscle result reports add force/activation coloring, picking, paired curves and CSV with physics/motion identity checks; volume reports preserve provenance. Muscle thickness is illustrative. Explicit linear data interpolation never extrapolates. Function-based paths without geometry are reported as unavailable. Reads only already-approved OBJ/STL/self-contained VTP and supported primitives; no textures/network. Sharing includes motion/model data. Visual sampling is not full-trial quality assessment."""
        from .viewer import export_animation
        return export_animation(cfg,api,motion_path,geometry_model_path,geometry_roots,comparison_motion_path,marker_path,max_frames,mesh_scale_factor,error_color_range_m,angles_in_degrees,
                                muscle_result_path,comparison_muscle_result_path,muscle_volume_path,muscle_data_interpolation)
    @mcp.tool(annotations=read,structured_output=True)
    def get_model_state(state_paths:list[str]|None=None,offset:int=0,limit:int=200)->dict[str,Any]:
        """Read bounded named native state values (positions, speeds, activations and other available states) without executing Python or changing revisions/undo. Paginate or select exact paths; native units apply."""
        from .core import InputError
        if type(offset) is not int or not 0<=offset<=5000 or type(limit) is not int or not 1<=limit<=200:raise InputError('Invalid native state page.')
        return api.call('native_state',dict(state_paths=state_paths,offset=offset,limit=limit))
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=False),structured_output=True)
    def edit_model_topology(operations:list[dict],expected_revision:int,dry_run:bool=True,label:str='',sync_gui:bool=False)->dict[str,Any]:
        """Preview/commit bounded body, Pin/Slider/Weld joint, marker and coordinate-actuator additions; whole set-member removal/rename and supported joint reconnection. Validates a candidate in another native process, preserves shared native states, commits as one undo step with full-state checkpoint/journal. Defaults to preview."""
        from .topology import apply_topology
        result=apply_topology(cfg,api,checkpoints,operations,expected_revision,dry_run,label)
        if sync_gui and result['committed']:
            try:result['gui_sync']=push_gui();result['gui_synchronized']=True
            except Exception as exc:result['gui_synchronized']=False;result['gui_error']=str(exc)
        return result
    @mcp.tool(annotations=write,structured_output=True)
    def reconfigure_gui_bridge(dry_run:bool=True,allow_legacy_stop:bool=False)->dict[str,Any]:
        """Preview/apply GUI bridge access roots from this server's existing configuration, preserving bridge identity and the current GUI model. Never accepts additional roots. Connected v1 bridges reload in place; legacy bridges require explicit allow_legacy_stop and a later GUI restart. Does not close the GUI."""
        from .gui_lifecycle import reconfigure_gui
        return reconfigure_gui(cfg,gui,dry_run,allow_legacy_stop)
    @mcp.tool(annotations=write,structured_output=True)
    def ensure_gui_connection(launch_if_closed:bool=False,wait_seconds:int=30)->dict[str,Any]:
        """Observe/wait for the auto bridge, optionally launch the configured GUI if none is running. Never closes another GUI or merges models. Reports actual bridge/core version and startup failure; durable identity permits queue recreation."""
        from .gui_lifecycle import ensure_gui
        return ensure_gui(cfg,gui,launch_if_closed,wait_seconds)
    @mcp.tool(annotations=read,structured_output=True)
    def get_recovery_status(limit:int=20)->dict[str,Any]:
        """List durable model/native-state recovery snapshots across server restarts, with owner identities. Recovery requires an explicit selected snapshot; no cross-chat model is restored automatically."""
        return api.recovery.status(limit)
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=False),structured_output=True)
    def recover_api_session(snapshot_id:str,discard_current:bool=False)->dict[str,Any]:
        """Restore a verified model plus all named native states/time after worker/server failure. Runtime must match. Replacing a live model requires discard_current=true and saves its recovery point. Does not replay scripts or restore GUI/files/Python variables."""
        return api.recovery.restore(snapshot_id,discard_current)
    @mcp.tool(annotations=write,structured_output=True)
    def create_biomechanics_project(name:str,model_path:str,static_marker_path:str,movement_marker_path:str,subject_mass_kg:float,
                                   body_scales:dict[str,list[float]],movable_markers:list[str],marker_weights:dict[str,float],lowpass_cutoff_hz:float,
                                   loads_path:str|None=None,external_forces:list[dict]|None=None,no_external_loads:bool=False,
                                   reserve_definitions:list[dict]|None=None,rra_settings:dict|None=None,quality_limits:dict[str,float]|None=None,
                                   residual_force_columns:list[str]|None=None,max_marker_movement_m:float=.02,max_static_motion_m:float=.01)->dict[str,Any]:
        """Create a strict reviewable scale/MarkerPlacer/IK/fit/ID/MuscleAnalysis/SO/JointReaction project, optionally RRA and explicit reserves. No guessed body scaling, external loads, actuator roles or physiological thresholds; validate_project then run_project explicitly."""
        from .templates import create_biomechanics_project as create
        return create(cfg,name,model_path,static_marker_path,movement_marker_path,subject_mass_kg,body_scales,movable_markers,marker_weights,lowpass_cutoff_hz,
            loads_path,external_forces,no_external_loads,reserve_definitions,rra_settings,quality_limits,residual_force_columns,max_marker_movement_m,max_static_motion_m)
    @mcp.tool(annotations=write,structured_output=True)
    def prepare_moco_model(model_path:str,replace_muscles_with_degroote:bool=True,ignore_tendon_compliance:bool=False,
                           ignore_passive_fiber_force:bool=False,reserve_definitions:list[dict]|None=None)->dict[str,Any]:
        """Create a native-initialized Moco model copy with explicitly selected DeGrooteFregly2016 conversion, tendon/passive changes and named reserve/residual actuators. Reports each muscle class before/after. Physics change is explicit and requires renewed validation."""
        from .moco_model import prepare_moco_model as prepare
        return prepare(cfg,model_path,replace_muscles_with_degroote,ignore_tendon_compliance,ignore_passive_fiber_force,reserve_definitions)
    @mcp.tool(annotations=write,structured_output=True)
    def run_moco_convergence(profile:str,parameters:dict,mesh_interval_values_s:list[float],state_rms_limits:dict[str,float]|None=None,
                             control_rms_limits:dict[str,float]|None=None,objective_relative_tolerance:float=.02,objective_absolute_tolerance:float=1e-8)->dict[str,Any]:
        """Run 2..4 native Track/Inverse refinements. Compare objective and interpolated full state/control trajectories; caller RMS thresholds decide assessed checks. Objective-only agreement is labeled separately. Prefer async moco_convergence for long solves."""
        from .studies import run_convergence
        return run_convergence(cfg,profile,parameters,mesh_interval_values_s,state_rms_limits,control_rms_limits,objective_relative_tolerance,objective_absolute_tolerance)
    @mcp.tool(annotations=write,structured_output=True)
    def run_moco_sensitivity(profile:str,parameters:dict,variations:list[dict])->dict[str,Any]:
        """Native baseline and 1..5 explicit physical model/goal perturbations. Returns objective and trajectory differences. Model edits use the bounded body/coordinate/marker/muscle parameter profile; user API session is unchanged. Prefer async moco_sensitivity."""
        from .studies import run_sensitivity
        return run_sensitivity(cfg,profile,parameters,variations)
    @mcp.tool(annotations=write,structured_output=True)
    def run_residual_reduction(model_path:str,coordinates_path:str,actuators:list[dict],task_weights:dict[str,float],
                               loads_path:str|None=None,external_forces:list[dict]|None=None,no_external_loads:bool=False,
                               start_time:float|None=None,end_time:float|None=None,lowpass_cutoff_hz:float=6.,adjust_com_body:str|None=None,
                               kp:float=100.,kv:float=20.,max_tracking_error:dict[str,float]|None=None,compare_inverse_dynamics:bool=True)->dict[str,Any]:
        """Native RRA using explicit torque/residual actuators/tasks. Restores original actuators in the adjusted model; optional COM adjustment and before/after ID residual assessment. No guessed roles, automatic mass recommendations or promised residual reduction. Use rra via submit_analysis for reliable cancellation."""
        from .rra import run_rra
        return run_rra(cfg,model_path,coordinates_path,actuators,task_weights,loads_path,external_forces,no_external_loads,start_time,end_time,lowpass_cutoff_hz,adjust_com_body,kp,kv,max_tracking_error,compare_inverse_dynamics)
    @mcp.tool(annotations=read,structured_output=True)
    def inspect_c3d_file(c3d_path:str)->dict[str,Any]:
        """Inspect trusted C3D markers, rates, units, gaps and force-platform count in an isolated native parser. Does not infer axes/sign or convert data."""
        from .c3d import inspect_c3d
        return inspect_c3d(cfg,c3d_path)
    @mcp.tool(annotations=write,structured_output=True)
    def import_c3d_trial(c3d_path:str,source_to_opensim_rotation:list[list[float]],plate_mappings:list[dict]|None=None,
                        force_sign:float|None=None,source_up_axis:str='Z',contact_threshold_N:float=20.,time_origin:str='zero',
                        marker_names:list[str]|None=None,marker_name_map:dict[str,str]|None=None)->dict[str,Any]:
        """Convert trusted C3D to meters TRC and N/m/Nm loads. Requires explicit proper rotation; plates need explicit index/body/name and force sign. Only source Z-up force filtering, no guessed side/sign or gap filling. COP free moment is used, not the moment about platform origin."""
        from .c3d import import_c3d
        return import_c3d(cfg,c3d_path,source_to_opensim_rotation,plate_mappings,force_sign,source_up_axis,contact_threshold_N,time_origin,marker_names,marker_name_map)
    @mcp.tool(annotations=read,structured_output=True)
    def validate_trial_inputs(model_path:str,marker_path:str,coordinates_path:str|None=None,loads_path:str|None=None,
                              external_forces:list[dict]|None=None,force_units:dict[str,str]|None=None)->dict[str,Any]:
        """Check model marker/coordinate coverage, units, external-load body/column mapping and common time window. No numerical solve or anatomical validation."""
        from .c3d import validate_trial
        return validate_trial(cfg,model_path,marker_path,coordinates_path,loads_path,external_forces,force_units)
