"""Explicit lower-limb device muscle studies and volume provenance."""
from typing import Any
from mcp.types import ToolAnnotations

def register_exoskeleton_tools(mcp,cfg):
    write=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)
    @mcp.tool(annotations=write,structured_output=True)
    def run_muscle_force_study(model_path:str,coordinates_path:str,actuator_profile:list[dict],quality_limits:dict[str,float],
                               loads_path:str|None=None,external_forces:list[dict]|None=None,no_external_loads:bool=False,
                               lowpass_cutoff_hz:float|None=None,label:str='',optimizer_max_iterations:int=2000)->dict[str,Any]:
        """Predict muscle tensions/activations with native SO and matched ID. Explicit reserve/residual profiles and all three numeric quality limits required. No automatic strengthening or actuator guessing. Reports per-muscle peaks/RMS/impulse, quality failures and original physics identity. Native optimizer failure aborts. Can return completed/needs_review; not physiological validation. Does not alter API/GUI."""
        from .muscle_forces import force_study
        return force_study(cfg,model_path,coordinates_path,actuator_profile,quality_limits,loads_path,external_forces,no_external_loads,lowpass_cutoff_hz,label,optimizer_max_iterations)
    @mcp.tool(annotations=write,structured_output=True)
    def compare_wearable_muscle_forces(baseline_model_path:str,assembly_report_path:str,coordinates_path:str,
                                      actuator_profile:list[dict],quality_limits:dict[str,float],loads_path:str|None=None,
                                      external_forces:list[dict]|None=None,no_external_loads:bool=False,
                                      lowpass_cutoff_hz:float|None=None,optimizer_max_iterations:int=2000)->dict[str,Any]:
        """Compare verified welded added device masses using identical motion, loads, muscle parameters, explicit actuators and SO settings. Validates assembly/source hashes. Reports baseline/wearable muscle forces and peak/mean/RMS/impulse differences with numeric quality. No active motor assistance, altered gait, strap/contact-pressure or clinical benefit inference."""
        from .muscle_forces import compare_studies
        return compare_studies(cfg,baseline_model_path,assembly_report_path,coordinates_path,actuator_profile,quality_limits,loads_path,external_forces,no_external_loads,lowpass_cutoff_hz,optimizer_max_iterations)
    @mcp.tool(annotations=write,structured_output=True)
    def estimate_muscle_volumes(model_path:str,specific_tension_Pa:float|None=None,measured_volumes_cm3:dict[str,float]|None=None,
                                measurement_source:str='')->dict[str,Any]:
        """Record explicitly supplied muscle volumes in cm3 with source, or estimate V=Fmax*optimal_fiber_length/specific_tension using explicit Pa assumption. No default specific tension or anatomy guessed from paths. Reports per-muscle provenance and model physics identity for viewer binding. Does not independently verify measurements or reconstruct anatomical shape."""
        from .muscle_forces import estimate_volumes
        return estimate_volumes(cfg,model_path,specific_tension_Pa,measured_volumes_cm3,measurement_source)
