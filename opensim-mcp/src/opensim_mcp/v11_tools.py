"""Structured v1.1 assembly, trial quality and coordination-facing tools."""
from typing import Any
from mcp.types import ToolAnnotations

def register_v11(mcp,cfg,api,gui):
    read=ToolAnnotations(readOnlyHint=True,openWorldHint=False)
    write=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)
    @mcp.tool(annotations=read,structured_output=True)
    def convert_body_mass_properties(properties:dict,frame_transform:dict)->dict[str,Any]:
        """Preview CAD mass/COM/inertia conversion without files or native/session changes. properties must explicitly give mass, mass_unit(kg/g), center_of_mass, length_unit(m/cm/mm), inertia(6:[xx,yy,zz,xy,xz,yz] or 9 row-major), inertia_unit(kg_m2/kg_mm2/g_mm2/g_cm2), inertia_reference(center_of_mass/source_origin), inertia_convention(tensor_entries/positive_products), source_frame and source_description. frame_transform requires target_frame, 3x3 rotation_source_to_target and translation_source_origin_in_target_m. Returns wearable body_parameters in kg/m/kg*m^2, central inertia in target axes and validation/provenance. Reject impossible principal moments, reflected/scaled frames and unstable parallel-axis subtraction. Does not transform mesh/joints, map anatomy, certify CAD inputs or run dynamics."""
        from .mass_properties import convert_mass_properties
        return convert_mass_properties(properties,frame_transform)
    @mcp.tool(annotations=write,structured_output=True)
    def compare_wearable_inverse_dynamics(baseline_model_path:str,assembly_report_path:str,coordinates_path:str,loads_path:str|None=None,
                                          external_forces:list[dict]|None=None,no_external_loads:bool=False,lowpass_cutoff_hz:float|None=None,
                                          assistance_path:str|None=None,assistance_mapping:list[dict]|None=None)->dict[str,Any]:
        """Compare baseline and verified welded-device ID on identical kinematics/loads/filter; quantify added mass demand. Optional ideal assist table needs every ID sample and explicit coordinate/column/N-or-Nm mapping. Remaining demand = combined ID minus assist. Reject changed models or articulated links needing study-specific force projection. Does not infer muscle/strap/contact forces or clinical benefit."""
        from .wearable_analysis import compare_id
        return compare_id(cfg,baseline_model_path,assembly_report_path,coordinates_path,loads_path,external_forces,no_external_loads,lowpass_cutoff_hz,assistance_path,assistance_mapping)
    @mcp.tool(annotations=write,structured_output=True)
    def audit_moco_trajectory(model_path:str,coordinates_path:str,states_path:str,controls_path:str,loads_path:str|None=None,
                              external_forces:list[dict]|None=None,no_external_loads:bool=False,ignore_tendon_compliance:bool=False)->dict[str,Any]:
        """Evaluate every exported state/control node (<=1000) in an explicit native model with the same external loads/tendon assumption. Report actual actuator outputs with N/Nm units, muscle activations, native control bounds and position/velocity constraint errors. Full states/controls and coincident nodes mandatory; not a forward replay, between-node defect or physiological proof."""
        from .trial_quality import audit_trajectory
        return audit_trajectory(cfg,model_path,coordinates_path,states_path,controls_path,loads_path,external_forces,no_external_loads,ignore_tendon_compliance)
    @mcp.tool(annotations=write,structured_output=True)
    def resample_coordinate_motion(coordinates_path:str,frequency_hz:float,start_time:float|None=None,end_time:float|None=None)->dict[str,Any]:
        """Create an explicitly requested uniform linear MOT/STO coordinate resampling, with source hash/window/rate. No extrapolation, smoothing, gap fill or angle unwrapping; retain inDegrees. Last full grid sample may precede requested end. Useful before filters that require uniform sampling."""
        from .trial_quality import resample_coordinates
        return resample_coordinates(cfg,coordinates_path,frequency_hz,start_time,end_time)
    @mcp.tool(annotations=read,structured_output=True)
    def inspect_gait_cycles(loads_path:str,vertical_force_column:str,on_threshold_N:float=20.,off_threshold_N:float=10.,
                            force_sign:float=1.,minimum_stance_s:float=.05,minimum_swing_s:float=.05)->dict[str,Any]:
        """Find complete same-foot/platform force-event cycles using an explicitly chosen upward force column in N, sign and hysteresis thresholds. Initial contact without observed onset is not a heel strike. First meeting source sample, no interpolation or guessed foot mapping; verify kinematic coverage."""
        from .trial_quality import gait_cycles
        return gait_cycles(cfg,loads_path,vertical_force_column,on_threshold_N,off_threshold_N,force_sign,minimum_stance_s,minimum_swing_s)
    @mcp.tool(annotations=read,structured_output=True)
    def assess_moco_mesh_study(study_report_path:str,state_rms_limits:dict[str,float],control_rms_limits:dict[str,float])->dict[str,Any]:
        """Assess a mesh study with caller RMS limits covering every named state and control exactly. Reject incomplete/extra columns and nonfinite metrics; report failed columns and objective check separately. Numeric assessment, not full mathematical/physiological validation."""
        from .trial_quality import assess_mesh
        return assess_mesh(cfg,study_report_path,state_rms_limits,control_rms_limits)
    @mcp.tool(annotations=write,structured_output=True)
    def assemble_wearable_model(model_path:str,links:list[dict],physical:bool=True,geometry_roots:list[str]|None=None,
                                max_landmark_error_m:float|None=None,open_in_gui:bool=False)->dict[str,Any]:
        """Attach trusted CAD meshes to a human-model copy. Each physical link explicitly supplies SI mass/COM/inertia and Weld/Pin/Slider joint; optional one-coordinate linear coupling. Explicit transform or >=3 corresponding CAD/body-frame landmarks. Mesh units mandatory. Visual-only mode adds offset frames without mass. Outputs portable model/meshes; does not guess strap/contact forces or alter API/source. Optional GUI open uses multi-session revision guard."""
        from .wearable import assemble
        result=assemble(cfg,model_path,links,physical,geometry_roots,max_landmark_error_m)
        if open_in_gui:
            try:result['gui']=gui.open_model(result['model_file']);result['gui_opened']=True
            except Exception as exc:result.update(gui_opened=False,gui_error=str(exc))
        return result
    @mcp.tool(annotations=write,structured_output=True)
    def prepare_wearable_motion(assembly_report_path:str,coordinates_path:str)->dict[str,Any]:
        """Copy a complete human motion and add only device coordinates defined by verified explicit linear couplings, respecting rad/m and inDegrees. Reject missing independent motion, coupling mismatch, changed assembly model or range violations. No resampling/guessed motion."""
        from .wearable import prepare_motion
        return prepare_motion(cfg,assembly_report_path,coordinates_path)
