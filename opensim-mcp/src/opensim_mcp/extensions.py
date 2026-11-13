from __future__ import annotations

import json
from typing import Any
import uuid
import asyncio

from mcp.server.fastmcp import Image
from mcp.types import ToolAnnotations

from .checkpoints import Checkpoints
from .core import InputError
from .diagnostics import check_code,diagnose_error
from .jobs import JobManager
from .media import image_bytes,plot_motion,render_model as render
from .workflows import run_scale,run_joint_reaction as joint_reaction,run_moco as moco_solve,assess_ik_quality as marker_quality


def register_extended(mcp,cfg,api,gui,push_gui):
    jobs=JobManager(cfg);checkpoints=Checkpoints(cfg,api)
    read=ToolAnnotations(readOnlyHint=True,openWorldHint=False)
    write=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)
    destructive=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=False)

    from .projects import Project,create_project as create,prepare_submission
    from .pipeline import get_run
    from .structured import place_markers as place,configure_actuators as actuators,assess_actuator_usage as usage
    from .tracking import moco_track,moco_inverse
    from .bundles import export_bundle,verify_bundle,import_bundle
    from .transactions import Transactions
    from .scene_export import export_scene
    transactions=Transactions(cfg,api,checkpoints)

    @mcp.tool(annotations=read,structured_output=True)
    def check_version_compatibility()->dict[str,Any]:
        """Probe installed native API/Python/NumPy and Moco/MarkerPlacer capabilities against tested Windows profiles. Reports unsupported/unknown combinations distinctly; import/symbol checks do not prove a solver run or GUI compatibility."""
        from .compatibility import check_runtime
        return check_runtime(cfg)

    @mcp.tool(annotations=write,structured_output=True)
    def export_project_bundle(project_path:str)->dict[str,Any]:
        """Bundle explicit project input data and configuration with hashes/runtime dependency metadata. Model XML is normalized to the self-contained native profile, display geometry removed. No credentials, scripts, meshes or runtimes. Includes input data: review sharing rights before publishing."""
        return export_bundle(cfg,project_path)

    @mcp.tool(annotations=read,structured_output=True)
    def verify_project_bundle(bundle_path:str)->dict[str,Any]:
        """Verify bounded ZIP inventory, paths, hash integrity and strict project graph without extraction or native execution. Hash integrity does not establish author trust or runtime compatibility."""
        return verify_bundle(cfg,bundle_path)

    @mcp.tool(annotations=write,structured_output=True)
    def import_project_bundle(bundle_path:str)->dict[str,Any]:
        """Verify and import a portable project to a fresh result folder, checking data/units without executing native models or hooks. Never overwrites inputs or grants additional roots."""
        return import_bundle(cfg,bundle_path)

    @mcp.tool(annotations=write,structured_output=True)
    def apply_model_edits(edits:list[dict],expected_revision:int,dry_run:bool=True,label:str='',sync_gui:bool=False)->dict[str,Any]:
        """Preview or atomically commit 1..50 supported model parameter edits. Requires observed revision; failures leave live model unchanged. Commit creates a durable before-checkpoint/journal and one undo step. GUI sync occurs after API commit and is reported separately."""
        result=transactions.apply(edits,expected_revision,dry_run,label)
        if sync_gui and not dry_run:
            try:result['gui_sync']=push_gui();result['gui_synchronized']=True
            except Exception as exc:result['gui_synchronized']=False;result['gui_error']=str(exc)
        return result

    @mcp.tool(annotations=read,structured_output=True)
    def list_edit_transactions(limit:int=50)->dict[str,Any]:
        """Read durable batch edit journal entries, including recovery checkpoints."""
        return transactions.list(limit)

    @mcp.tool(annotations=destructive,structured_output=True)
    def rollback_edit_transaction(transaction_id:str,expected_revision:int,sync_gui:bool=False)->dict[str,Any]:
        """Restore the pre-transaction model/pose/time checkpoint, requiring the currently observed revision; a recovery checkpoint preserves current state. Later model edits are replaced by this rollback."""
        result=transactions.rollback(transaction_id,expected_revision)
        if sync_gui:
            try:result['gui_sync']=push_gui();result['gui_synchronized']=True
            except Exception as exc:result['gui_synchronized']=False;result['gui_error']=str(exc)
        return result

    @mcp.tool(annotations=write,structured_output=True)
    def export_model_scene()->dict[str,Any]:
        """Export actual API native 3D body-frame/marker coordinates in meters, standalone SVG orthogonal views and a self-contained HTML viewer. No surface meshes or animation; pull GUI state explicitly to export its pose."""
        return export_scene(cfg,api.call('scene'))

    @mcp.tool(annotations=write,structured_output=True)
    def run_moco_track(model_path:str,coordinates_path:str,initial_time:float,final_time:float,state_bounds:dict,control_bounds:dict,
                       loads_path:str|None=None,external_forces:list[dict]|None=None,no_external_loads:bool=False,
                       tracking_weight:float=1.,control_effort_weight:float=.001,track_reference_derivatives:bool=True,
                       mesh_interval:float=.05,max_iterations:int=500,convergence_tolerance:float=1e-4,constraint_tolerance:float=1e-4,
                       max_tracking_rms:dict[str,float]|None=None)->dict[str,Any]:
        """Structured coordinate-reference MocoTrack. Requires complete rad/m state bounds, control bounds, all-coordinate motion with explicit inDegrees, and loads or no-load opt-in. Reports coordinate tracking RMS/peaks and feasibility; use moco_track via submit_analysis for cancellation."""
        return moco_track(cfg,model_path,coordinates_path,initial_time,final_time,state_bounds,control_bounds,loads_path,external_forces,no_external_loads,
                          tracking_weight,control_effort_weight,track_reference_derivatives,mesh_interval,max_iterations,convergence_tolerance,constraint_tolerance,max_tracking_rms)

    @mcp.tool(annotations=write,structured_output=True)
    def run_moco_inverse(model_path:str,coordinates_path:str,initial_time:float,final_time:float,loads_path:str|None=None,
                         external_forces:list[dict]|None=None,no_external_loads:bool=False,ignore_tendon_compliance:bool=False,
                         minimize_sum_squared_activations:bool=False,mesh_interval:float=.05,max_iterations:int=500,
                         convergence_tolerance:float=1e-4,constraint_tolerance:float=1e-4)->dict[str,Any]:
        """Structured MocoInverse with all-coordinate prescribed motion and explicit external-load assumption. Existing native actuator/control bounds apply; no automatic reserves. Optional tendon-compliance change is explicit. Reports convergence and sampled coordinate differences; prefer async moco_inverse."""
        return moco_inverse(cfg,model_path,coordinates_path,initial_time,final_time,loads_path,external_forces,no_external_loads,
                            ignore_tendon_compliance,minimize_sum_squared_activations,mesh_interval,max_iterations,convergence_tolerance,constraint_tolerance)

    @mcp.tool(annotations=write,structured_output=True)
    def place_model_markers(model_path:str,static_marker_path:str,movable_markers:list[str],marker_weights:dict[str,float],
                            coordinate_targets:dict[str,dict]|None=None,start_time:float|None=None,end_time:float|None=None,
                            max_marker_movement_m:float=.02,max_static_motion_m:float=.01)->dict[str,Any]:
        """Run native MarkerPlacer on an already scaled model, moving only named markers. Static TRC, IK weights and movement limits are explicit; optional manual coordinate targets use rad/m. Saves a new initialized model and one-frame static pose."""
        return place(cfg,model_path,static_marker_path,movable_markers,marker_weights,coordinate_targets,start_time,end_time,max_marker_movement_m,max_static_motion_m)

    @mcp.tool(annotations=write,structured_output=True)
    def configure_model_actuators(model_path:str,definitions:list[dict])->dict[str,Any]:
        """Add explicit CoordinateActuators to a new model. Each definition needs name, coordinate, reserve/residual role, N/Nm unit, optimal_force, min_control and max_control. Reject existing coordinate actuators and locked/dependent coordinates; native readback validates units."""
        return actuators(cfg,model_path,definitions)

    @mcp.tool(annotations=write,structured_output=True)
    def assess_actuator_usage(model_path:str,forces_path:str,definitions:list[dict],reference_path:str|None=None)->dict[str,Any]:
        """Report actuator force/moment RMS and peaks; optional ratios to explicit ID/reference columns on coincident samples. Definitions: name, role, unit, force_column, optional reference_column. Zero reference is not assessed; no implicit acceptance threshold."""
        return usage(cfg,model_path,forces_path,definitions,reference_path)

    @mcp.tool(annotations=read,structured_output=True)
    def get_project_schema()->dict[str,Any]:
        """Return the strict versioned portable project JSON schema. References track inputs and earlier stage outputs; a project cannot grant roots or select executables."""
        return Project.model_json_schema()

    @mcp.tool(annotations=write,structured_output=True)
    def create_project(config:dict[str,Any])->dict[str,Any]:
        """Validate and save a project under results, using existing absolute allowlisted inputs. No source file is overwritten."""
        return create(cfg,config)

    @mcp.tool(annotations=read,structured_output=True)
    def validate_project(project_path:str)->dict[str,Any]:
        """Check strict project shape, ordered dependencies, asset types/units and input hashes without running native solvers."""
        return {'valid':True,**prepare_submission(cfg,project_path)}

    @mcp.tool(annotations=write,structured_output=True)
    def run_project(project_path:str,resume:bool=True,timeout_seconds:int=600)->dict[str,Any]:
        """Submit a staged asynchronous project. Reuse only hash-verified stages with matching inputs/settings/runtime/source. Completed stage checkpoints survive cancellation; incomplete stages do not. Poll/cancel through job tools."""
        return jobs.submit('pipeline',dict(project_path=project_path,resume=resume),timeout_seconds)

    @mcp.tool(annotations=read,structured_output=True)
    def get_project_run(run_id:str)->dict[str,Any]:
        """Read persistent stage/cache history, measured quantities and quality-report location, including failed/interrupted runs."""
        return get_run(cfg,run_id)

    def media(result):
        return [json.dumps(result,ensure_ascii=False),Image(data=image_bytes(cfg,result['image_file']),format='png')]

    def modern_gui(op,args=None):
        status=gui.call('status')
        if status.get('bridge_version') not in {'0.4.0','1.0.0','1.1.0'}:raise InputError('Restart OpenSim once to load a supported GUI bridge.')
        return gui.call(op,args)

    @mcp.tool(annotations=write,structured_output=True)
    def submit_analysis(workflow:str,parameters:dict[str,Any],timeout_seconds:int|None=None)->dict[str,Any]:
        """Submit isolated asynchronous native workflows, including muscle_force_study, wearable_muscle_comparison and muscle_volumes. Parameters match the corresponding synchronous tool. Returns immediately; poll get_job_status or cancel_job. No arbitrary scripts or persistent API session mutation."""
        return jobs.submit(workflow,parameters,timeout_seconds)

    @mcp.tool(annotations=read,structured_output=True)
    def get_job_status(job_id:str)->dict[str,Any]:
        """Read durable job state, actual workflow phase, native log tail and completed result. Solver completion percentage is unknown. Interrupted server runs are distinguished from completion."""
        return jobs.get(job_id)

    @mcp.tool(annotations=destructive,structured_output=True)
    def cancel_job(job_id:str)->dict[str,Any]:
        """Cancel a queued/running isolated workflow, stop its Windows process tree and prevent result publication. cancelled=true is returned only after confirmed termination. If completion committed first, returns completed."""
        return jobs.cancel(job_id)

    @mcp.tool(annotations=read,structured_output=True)
    def list_jobs(limit:int=50,status:str|None=None)->dict[str,Any]:
        """Read durable analysis history across MCP restarts; optional state filter and newest-first bounded list."""
        return jobs.list(limit,status)

    @mcp.tool(annotations=write,structured_output=True)
    def create_checkpoint(label:str='')->dict[str,Any]:
        """Save API model definition, coordinate pose, time, runtime version and hash under results. Does not serialize arbitrary Python variables or external side effects."""
        return checkpoints.create(label)

    @mcp.tool(annotations=read,structured_output=True)
    def list_checkpoints(limit:int=50)->dict[str,Any]:
        """List persistent model/pose savepoints from newest to oldest."""
        return checkpoints.list(limit)

    @mcp.tool(annotations=destructive,structured_output=True)
    def restore_checkpoint(checkpoint_id:str,allow_version_mismatch:bool=False,sync_gui:bool=False)->dict[str,Any]:
        """Verify hash/runtime and restore the API model/pose/time; preserve a recovery savepoint first. Cross-version restore requires explicit opt-in and native initialization. Python variables are outside the savepoint scope."""
        result=checkpoints.restore(checkpoint_id,allow_version_mismatch)
        if sync_gui:result['gui_sync']=push_gui()
        return result

    @mcp.tool(annotations=destructive,structured_output=True)
    def undo_model_edit(expected_revision:int|None=None,sync_gui:bool=False)->dict[str,Any]:
        """Undo the last structured API parameter edit, retaining up to ten edits in memory. Guard with expected_revision. Arbitrary scripts/model loads clear undo history; filesystem effects cannot be undone."""
        result=api.call('undo',{'expected_revision':expected_revision})
        if sync_gui:result['gui_sync']=push_gui()
        return result

    @mcp.tool(annotations=destructive,structured_output=True)
    def redo_model_edit(expected_revision:int|None=None,sync_gui:bool=False)->dict[str,Any]:
        """Redo a structured parameter edit after undo, with optional revision guard and GUI push."""
        result=api.call('redo',{'expected_revision':expected_revision})
        if sync_gui:result['gui_sync']=push_gui()
        return result

    @mcp.tool(annotations=read,structured_output=True)
    def get_api_documentation(symbol:str='',query:str='',limit:int=50)->dict[str,Any]:
        """Discover actual installed OpenSim symbols or inspect public Class.method docs/member names without executing user code. Version-specific, bounded output."""
        return api.call('documentation',{'symbol':symbol,'query':query,'limit':limit})

    @mcp.tool(annotations=read,structured_output=True)
    def list_model_components(query:str='',class_name:str='',offset:int=0,limit:int=50)->dict[str,Any]:
        """List actual native model component paths/classes with filtering and pagination."""
        return api.call('components',dict(query=query,class_name=class_name,offset=offset,limit=limit))

    @mcp.tool(annotations=read,structured_output=True)
    def get_component_details(component_path:str)->dict[str,Any]:
        """Read a native component's public properties and socket connectee paths by absolute model path."""
        return api.call('component_details',{'component_path':component_path})

    @mcp.tool(annotations=read,structured_output=True)
    def check_opensim_code(code:str,filename:str='<mcp>',check_api_symbols:bool=True)->dict[str,Any]:
        """Check Python syntax and direct OpenSim API symbol existence, returning line/column diagnostics. Never executes the supplied code. Does not prove types, model validity or solver feasibility."""
        result=check_code(code,filename)
        if result['valid_syntax'] and check_api_symbols and result['symbols']:
            known=api.call('symbols',{'names':sorted({s['symbol'] for s in result['symbols']})})['symbols']
            for item in result['symbols']:
                if not known[item['symbol']]:result['diagnostics'].append(dict(item,severity='error',kind='unknown_api_symbol',message='Installed OpenSim has no '+item['symbol']))
            result['api_symbols_checked']=True
        return result

    @mcp.tool(annotations=read,structured_output=True)
    def diagnose_opensim_error(error_text:str)->dict[str,Any]:
        """Locate traceback files/lines and attach targeted input/runtime/solver hints. Text is analyzed as data; no code is executed."""
        return diagnose_error(error_text)

    @mcp.tool(annotations=write,structured_output=False)
    async def plot_motion_result(result_path:str,columns:list[str],title:str='',ylabel:str='Value (file units)')->list[Any]:
        """Create standalone PNG/SVG curves with explicit columns/units and return the actual PNG image to the MCP client. Large series use min/max decimation preserving spikes."""
        result=await asyncio.to_thread(plot_motion,cfg,result_path,columns,title,ylabel)
        return media(result)

    @mcp.tool(annotations=write,structured_output=False)
    async def render_model()->list[Any]:
        """Render actual API pose as body-frame skeleton/markers and return a PNG plus SVG. Uses native state positions in meters; surface meshes are excluded. Pull GUI state first to render its pose."""
        scene=await asyncio.to_thread(api.call,'scene')
        return media(await asyncio.to_thread(render,cfg,scene))

    @mcp.tool(annotations=read,structured_output=False)
    def read_image(image_path:str)->list[Any]:
        """Return an allowed bounded PNG as MCP image content, rather than a path-only response."""
        return [Image(data=image_bytes(cfg,image_path),format='png')]

    @mcp.tool(annotations=write,structured_output=False)
    def capture_gui_image()->list[Any]:
        """Capture only the OpenSim Swing window and return PNG content. Hardware-accelerated 3D/browser surfaces can be blank; render_model provides native pose geometry independently."""
        folder=cfg.results_root/('gui-image-'+uuid.uuid4().hex);folder.mkdir(parents=True)
        return media(modern_gui('snapshot_png',{'destination':str(folder/'gui.png')}))

    @mcp.tool(annotations=read,structured_output=True)
    def get_gui_selection()->dict[str,Any]:
        """Read the actual OpenSim Navigator selection, including native object/component identity when the selected node exposes it."""
        return modern_gui('selection')

    @mcp.tool(annotations=write,structured_output=True)
    def select_gui_component(component_path:str)->dict[str,Any]:
        """Select an existing component in OpenSim's Navigator and read back its actual selection."""
        return modern_gui('select_component',{'component_path':component_path})

    @mcp.tool(annotations=destructive,structured_output=True)
    def undo_gui_pose()->dict[str,Any]:
        """Undo the last bridge coordinate edit (up to twenty). Reject undo if GUI model/pose changed since that edit. Does not undo arbitrary GUI/file operations."""
        return modern_gui('undo_pose')

    @mcp.tool(annotations=write,structured_output=True)
    def scale_model(model_path:str,subject_mass_kg:float,body_scales:dict[str,list[float]]|None=None,
                    static_marker_path:str|None=None,measurements:list[dict]|None=None,
                    preserve_mass_distribution:bool=True,max_measurement_error_m:float|None=None)->dict[str,Any]:
        """Native manual/marker-pair model scaling with explicit target mass. Measurement entries specify body, axes and marker_pairs. Returns mass/distance checks and reopened output. Does not relocate virtual markers with MarkerPlacer."""
        return run_scale(cfg,model_path,subject_mass_kg,body_scales,static_marker_path,measurements,preserve_mass_distribution,max_measurement_error_m)

    @mcp.tool(annotations=write,structured_output=True)
    def run_joint_reaction(model_path:str,coordinates_path:str,loads_path:str|None=None,
                           external_forces:list[dict[str,str]]|None=None,no_external_loads:bool=False,
                           start_time:float|None=None,end_time:float|None=None,lowpass_cutoff_hz:float|None=None,
                           joint_names:list[str]|None=None,on_body:str='child',in_frame:str='ground',
                           forces_path:str|None=None,ignore_actuators:bool=False)->dict[str,Any]:
        """Run native JointReaction with explicit external loads/no-load assumption, selected joints and reporting body/frame. Models with actuators require a complete force table or explicit ignore_actuators. Returns finite force/moment tables and peak resultants."""
        return joint_reaction(cfg,model_path,coordinates_path,loads_path,external_forces,no_external_loads,start_time,end_time,
                              lowpass_cutoff_hz,joint_names,on_body,in_frame,forces_path,ignore_actuators)

    @mcp.tool(annotations=write,structured_output=True)
    def run_moco(model_path:str,initial_time:float,final_time:float,state_bounds:dict[str,dict],
                 control_bounds:dict[str,list[float]],control_effort_weight:float=1.0,mesh_intervals:int=20,
                 max_iterations:int=500,convergence_tolerance:float=1e-4,constraint_tolerance:float=1e-4,
                 refine_mesh:bool=False,max_mesh_objective_relative_change:float=.02)->dict[str,Any]:
        """Fixed-time Moco/CasADi optimal control using complete explicit state/control bounds and a control-effort goal. Checks solver success, finite trajectory, endpoint/bound violations and optional doubled-mesh objective stability. Prefer submit_analysis for progress/cancellation."""
        return moco_solve(cfg,model_path,initial_time,final_time,state_bounds,control_bounds,control_effort_weight,mesh_intervals,
                          max_iterations,convergence_tolerance,constraint_tolerance,refine_mesh,max_mesh_objective_relative_change)

    @mcp.tool(annotations=write,structured_output=True)
    def assess_ik_quality(model_path:str,coordinates_path:str,marker_path:str,markers:list[str]|None=None,
                          max_frames:int=200,rms_threshold_m:float|None=None,interpolation:str='none')->dict[str,Any]:
        """Calculate native marker-position RMS/max residuals and per-marker errors. Default requires coincident samples; explicitly select interpolation=linear for different time grids (no extrapolation). Returns sampling/interpolation details and optional caller threshold."""
        return marker_quality(cfg,model_path,coordinates_path,marker_path,markers,max_frames,rms_threshold_m,interpolation)

    from .v1_tools import register_v1
    register_v1(mcp,cfg,api,gui,push_gui,checkpoints,transactions)
    from .v11_tools import register_v11
    register_v11(mcp,cfg,api,gui)
