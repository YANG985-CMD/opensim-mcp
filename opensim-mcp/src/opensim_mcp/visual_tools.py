"""Cross-application numeric data exchange; independent of body region."""
from typing import Any
from mcp.types import ToolAnnotations


def register_visual_tools(mcp, cfg):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False), structured_output=True)
    def create_visualization_workbench(scenes:list[dict], max_time_delta_s:float, component_mapping:list[dict]|None=None, view_state_path:str|None=None)->dict[str, Any]:
        """Create a simple offline one/two-scene 3D comparison workspace. Each scene requires animation.json path, label and explicit time_offset_s. Shared overlap timeline uses nearest native samples only within max_time_delta_s; unmatched poses are hidden. Supports linked cameras/selection, distance/three-point angle measures, curves/differences, visibility and portable view-state save/restore. Optional one-to-one left/right component mappings and exact-input-bound saved state. No automatic registration, live sync, anatomical joint-angle or surface clearance inference."""
        from .workbench import create_workbench
        return create_workbench(cfg,scenes,max_time_delta_s,component_mapping,view_state_path)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False), structured_output=True)
    def attach_visualization_signals(scene_path:str, signal_sources:list[dict])->dict[str, Any]:
        """Bind MATLAB/CSV/MOT/STO signals to an exported native animation.json. Requires explicit time column, s/ms units, offset, interpolation and gap limit; channel labels/units and optional known body/frame/muscle/coordinate/marker mapping. Reject extrapolation, missing data and stale optional physics signatures. Creates an offline 3D/curve workspace, copies numeric sources and records hashes. No native model change or cross-software live synchronization."""
        from .visual_signals import attach_signals
        return attach_signals(cfg, scene_path, signal_sources)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False), structured_output=True)
    def inspect_visualization_workspace(project_path:str)->dict[str, Any]:
        """Verify a visualization.json workspace, bounded local asset paths and every file hash; list component identifiers and signal provenance. No scripts, CAD or native models are executed; integrity does not establish source trust or physical equivalence."""
        from .visual_signals import inspect_workspace
        return inspect_workspace(cfg, project_path)
