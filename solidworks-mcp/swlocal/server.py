"""Explicit MCP tool surface; no eval/exec, macro tool, or active-document fallback."""
import atexit
import json
import os
from pathlib import Path
import tempfile
from typing import Literal
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from .broker import Broker,CadError
from .delivery import DeliveryChecks
from .tool_search import find_tools
from .acceptance import render_report, write_report
from .revision import package_paths
from .task_journal import AssemblyJournal

MCP_WORKFLOW = (
    'Use this native SolidWorks MCP for supported CAD operations. Start with sw_health, '
    'then sw_connect or sw_documents, and use sw_find_tools for supported operations. '
    'Follow the MCP recovery guidance. If the native bridge is blocked or no tool supports '
    'the task, report the exact blocker and pause. Do not switch to Computer Use, screen '
    'automation, or alternate CAD write paths unless the user explicitly asks to switch. '
)

mcp=FastMCP('solidworks-mcp',instructions=MCP_WORKFLOW+'Operate serially on explicit document_id handles. Every edit except creating a document requires its current state token. Inspect geometry again after every edit. Never reuse old edge/face IDs. A timeout may have partially changed CAD: inspect before any further edit. Use millimetres and degrees except dimension tools, which explicitly use SI system values. Assembly motion is kinematic, not a physical load or motor simulation. For a flexible muscle preview use sw_set_assembly_pose to update drivers and part dimensions within one call, never separate pose/length mutations. Default delivery policy: organize large assembly trees into a few descriptive module folders and collapse them; preserve independent parts, mates and export geometry. Use stable unique project/module/serial identifiers plus concise descriptive file names, distinguish mirrored L/R parts, keep revision in release metadata, reuse actual identical standard parts, and keep STLs named after their source part. Use reference-aware packaging for saved-file renaming, never raw filesystem rename. Verify reopening, native mates and STL before claiming organization did not affect exports. Avoid clutter from duplicate pose files or temporary prefixes in final deliveries. When separate-part or printing delivery is required, one whole-assembly STL is not a substitute for part STLs. Export once per unique native part with instance quantities in a manifest; explicitly exclude nonprinting placeholders such as the pneumatic muscle. Separate custom structural parts, purchased/envelope references and soft-part references; never infer load-bearing print suitability from an STL file. Report incomplete exports as incomplete. No macro or arbitrary-code tool is available. Completion/resource policy: after a PART is complete and required checks/exports are done, call sw_save with close_when_finished=True, verify window_cleanup, and continue with the next part; do not accumulate completed part windows. Intermediate checkpoint saves keep close_when_finished=False. Leave the current assembly open for review. Close only the explicit saved window, keep assembly references, and preserve all unknown unsaved work. If cleanup is skipped, explain the reason and address only explicitly owned work; never bulk-discard, kill/restart SOLIDWORKS or weaken memory guards. Close-after-save is not a geometry/strength acceptance check. For file delivery, capture expected paths with sw_delivery_baseline before generation and call sw_verify_delivery after export. Treat unchanged, missing or empty outputs as needs_review. Use sw_find_tools when you need to discover an appropriate tool.')
broker=None

CAD_RECOVERY = {
    'NOT_RUNNING': ('sw_connect', 'Start SOLIDWORKS normally or call sw_connect(start_if_needed=True) when launching it is intended.'),
    'RUNNING_NOT_READY': (None, 'Wait for SOLIDWORKS to finish starting and check that it is running under the same Windows user and privilege level as Codex. Then retry sw_connect.'),
    'TYPELIB_MISSING': (None, 'Run the share installer on this computer, or set SWLOCAL_TYPELIB to the installed SOLIDWORKS 2025 sldworks.tlb and reload the MCP.'),
    'TYPELIB_LOAD_FAILED': (None, 'Verify or reinstall the SOLIDWORKS 2025 type library and reload the MCP.'),
    'TYPELIB_VERSION_MISMATCH': (None, 'Configure the type library from the SOLIDWORKS 2025 installation and reload the MCP.'),
    'VERSION_MISMATCH': (None, 'Use the installed SOLIDWORKS 2025 instance. The bridge has not accepted the other version.'),
    'DOCUMENT_HANDLE': ('sw_documents', 'Get a fresh document handle, then read its state with sw_geometry.'),
    'DOCUMENT_CLOSED': ('sw_documents', 'List current documents. Reopen the intended file only if needed.'),
    'STALE_STATE': ('sw_geometry', 'Read the current state and geometry before deciding on another edit.'),
    'CAD_TIMEOUT': ('sw_connect', 'Reconnect, then read the current document and geometry before any edit. The prior write may have partially completed.'),
    'WORKER_PROTOCOL': ('sw_health', 'Probe the bridge. If the worker still fails, check worker.log under the configured runtime directory. Inspect any partial CAD write before retrying.'),
}

def call(operation,arguments=None,write=False):
    global broker
    if broker is None: broker=Broker()
    try: return broker.request(operation,arguments or {},mutating=write)['data']
    except CadError as error:
        payload = dict(error.payload)
        next_tool, recovery = CAD_RECOVERY.get(
            payload.get('code'), (None, 'Report this native error. Inspect the current document before attempting another edit.'))
        payload.update(next_tool=next_tool, recovery=recovery)
        raise ToolError(json.dumps(payload,ensure_ascii=False)) from error

TOOL_LABELS = {
    "sw_health": "连接状态",
    "sw_connect": "连接软件",
    "sw_documents": "文档列表",
    "sw_new_document": "新建文档",
    "sw_open_document": "打开文档",
    "sw_import_step": "导入 STEP",
    "sw_geometry": "检查几何",
    "sw_features": "特征与尺寸",
    "sw_box": "创建长方体",
    "sw_cylinder": "创建圆柱",
    "sw_polygon": "拉伸轮廓",
    "sw_through_hole": "创建通孔",
    "sw_fillet": "添加圆角",
    "sw_set_dimension": "修改尺寸",
    "sw_save": "保存文档",
    "sw_export": "导出模型",
    "sw_close": "关闭文档",
    "sw_add_component": "插入组件",
    "sw_component_geometry": "检查组件",
    "sw_mate_cylinders": "圆柱同心配合",
    "sw_set_component_fixed": "固定或浮动组件",
    "sw_add_mate": "添加配合",
    "sw_assembly_status": "装配状态",
    "sw_set_mate_position": "设置配合位置",
    "sw_move_component": "移动组件",
    "sw_check_interference": "检查干涉",
    "sw_audit_assembly": "装配体检",
    "sw_mass_properties": "质量与惯量",
    "sw_materials": "查询材料",
    "sw_set_material": "设置材料",
    "sw_api_lookup": "查询 API",
    "sw_add_components": "批量插入组件",
    "sw_connect_rigid_group": "连接刚体组",
    "sw_create_joint": "创建关节",
    "sw_set_mate_positions": "批量设置配合位置",
    "sw_set_dimensions": "批量修改尺寸",
    "sw_scan_motion": "检查运动姿态",
    "sw_set_mate_suppressed": "抑制或恢复配合",
    "sw_organize_assembly": "整理装配树",
    "sw_package_assembly": "打包装配副本",
    "sw_set_mate_flips": "调整配合方向",
    "sw_set_assembly_pose": "设置完整姿态",
    "sw_close_reference_views": "关闭引用件窗口",
    "sw_find_tools": "查找工具",
    "sw_delivery_baseline": "记录交付基线",
    "sw_verify_delivery": "核验交付文件",
    "sw_compare_assemblies": "比较装配版本",
    "sw_capture_joint_recipe": "保存机构配方",
    "sw_apply_joint_recipe": "应用机构配方",
    "sw_run_assembly_steps": "执行装配任务",
    "sw_assembly_task_status": "查看任务记录",
    "sw_verify_package_references": "核验装配引用",
    "sw_write_acceptance_report": "生成验收报告",
}


def tool(read=False, destructive=False):
    def register(fn):
        title = 'SolidWorks MCP · ' + TOOL_LABELS[fn.__name__]
        return mcp.tool(title=title, annotations={
            'title': title, 'readOnlyHint': read, 'destructiveHint': destructive, 'openWorldHint': False,
        })(fn)
    return register

@tool(read=True)
def sw_health()->dict:
    """Check MCP connectivity, bridge version, and the configured SOLIDWORKS type library without starting CAD. MCP 连接与安装诊断。"""
    return call('health')

@tool()
def sw_connect(start_if_needed:bool=False,visible:bool=True)->dict:
    """Attach through the native SOLIDWORKS 2025 API. Launch only if explicitly requested and none is running. 连接 SolidWorks。"""
    return call('connect',locals())

@tool(read=True)
def sw_documents()->dict:
    """List exact document handles. Merely discovering a document never makes it editable."""
    return {'documents':call('list_documents')}

@tool()
def sw_new_document(kind:Literal['part','assembly']='part')->dict:
    """Create a new editable document from its explicit native template."""
    return call('new_document',locals(),True)

@tool()
def sw_open_document(path:str,editable:bool=False,state:str|None=None)->dict:
    """Open a native file. editable=False makes a newly opened native file read-only, but does not downgrade an already-open file. editable=True permits edits. For an ALREADY open native read-only document, provide its fresh sw_geometry state to request in-place SetReadOnlyState(False); verify geometry/mates and unsaved flag unchanged. Never closes/reopens, saves, discards, changes filesystem permissions or bypasses another writer's lock. sw_documents distinguishes native_read_only from MCP editable permission."""
    return call('open_document',locals(),write=editable)

@tool()
def sw_import_step(path:str)->dict:
    """Import one STEP staged inside the configured project output root as a new native solid part using official LoadFile4. Returns an editable document handle and fresh geometry. Preserves the input hash, retains source units, refuses repeat import of an already open input. No feature-recognition or material/mass inference. Native failure may have opened a document: inspect before retry."""
    return call('import_step',locals(),True)

@tool(read=True)
def sw_geometry(document_id:str)->dict:
    """Read the current state token, solid volume, bounds, and edge/face IDs. No concavity guessing."""
    return call('snapshot',locals())

@tool(read=True)
def sw_features(document_id:str)->dict:
    """Read feature tree and exact dimension names with SI values and native dimension types."""
    return call('features',locals())

@tool()
def sw_box(document_id:str,state:str,width_mm:float,height_mm:float,depth_mm:float)->dict:
    """Create a fully defined centred rectangle and positive-depth extrusion in an empty part; verify volume."""
    return call('box',locals(),True)

@tool()
def sw_cylinder(document_id:str,state:str,diameter_mm:float,depth_mm:float)->dict:
    """Create a fully defined centred circular extrusion in an empty part and verify volume."""
    return call('cylinder',locals(),True)

@tool()
def sw_polygon(document_id:str,state:str,vertices_mm:list[tuple[float,float]],depth_mm:float)->dict:
    """Extrude a simple non-self-intersecting polygon in an empty part; verify area times depth."""
    return call('polygon',locals(),True)

@tool()
def sw_through_hole(document_id:str,state:str,diameter_mm:float,x_mm:float=0.,y_mm:float=0.)->dict:
    """Cut a front-plane through hole. Determine material side before the single native cut; verify cylindrical wall and volume removal."""
    return call('through_hole',locals(),True)

@tool()
def sw_fillet(document_id:str,state:str,edge_ids:list[int],radius_mm:float)->dict:
    """Fillet exact edges from a fresh geometry state and verify a solid volume change."""
    return call('fillet',locals(),True)

@tool()
def sw_set_dimension(document_id:str,state:str,dimension_name:str,value_si:float)->dict:
    """Set an exact existing dimension returned by sw_features. SI units: metres for lengths, radians for angles. Read back and rebuild."""
    return call('set_dimension',locals(),True)

@tool()
def sw_save(document_id:str,state:str,path:str,overwrite:bool=False,close_when_finished:bool=False)->dict:
    """Save native SLDPRT/SLDASM; verify native error flags and file hash. For a completed PART, set close_when_finished=True AFTER required exports/checks: close only its saved window, retain referenced geometry and verify parent references/poses/mates/unsaved flags. Unknown hidden unsaved docs block cleanup and remain open; never discard/restart. Intermediate saves leave False. Assemblies stay open for review. On unload state=None and document_handle_valid=False: reopen before editing. A close failure explicitly reports that saving already succeeded; inspect, never repeat automatically."""
    return call('save',locals(),True)

@tool()
def sw_export(document_id:str,state:str,path:str,overwrite:bool=False)->dict:
    """Export STEP or STL inside the configured output root; never silently overwrite a different file."""
    return call('export',locals(),True)

@tool(destructive=True)
def sw_close(document_id:str,discard_changes:bool=False)->dict:
    """Close only the named document. Refuse unsaved changes unless discard_changes is explicitly true."""
    return call('close',locals(),True)

@tool()
def sw_add_component(document_id:str,state:str,path:str,x_mm:float=0.,y_mm:float=0.,z_mm:float=0.,fixed:bool=False)->dict:
    """Insert a native part in the specified assembly. Set and read back exact placement and fixed state."""
    return call('add_component',locals(),True)

@tool(read=True)
def sw_component_geometry(document_id:str,component_name:str)->dict:
    """Inspect one top-level assembly component; face IDs are in part-local coordinates and guarded by assembly state."""
    return call('component_geometry',locals())

@tool()
def sw_mate_cylinders(document_id:str,state:str,component_a:str,face_a:int,component_b:str,face_b:int)->dict:
    """Create a native concentric mate between exact cylindrical faces mapped into assembly context."""
    return call('mate_cylinders',locals(),True)

@tool()
def sw_set_component_fixed(document_id:str,state:str,component_name:str,fixed:bool)->dict:
    """Fix or float one exact top-level component and verify its native state. Does not delete mates."""
    return call('set_component_fixed',locals(),True)

@tool()
def sw_add_mate(document_id:str,state:str,mate_type:Literal['coincident','concentric','parallel','perpendicular','distance','angle','limit_distance','limit_angle','lock'],reference_a:dict,reference_b:dict,value:float=0.,minimum:float=0.,maximum:float=0.,alignment:Literal['aligned','anti_aligned','closest']='closest',lock_rotation:bool=False,flip:bool=False,name:str='')->dict:
    """Create a real native mate. References: {component, face_id} or {component, plane_name} from fresh sw_component_geometry. Lock uses {component} references. Distance is mm; angle is degrees. Limit values must be nonnegative; use offset reference planes for signed joint ranges. Check native feature errors, read back bounds and inspect assembly status. Failure may leave a partial mate; never blindly retry."""
    return call('add_mate',locals(),True)

@tool(read=True)
def sw_assembly_status(document_id:str)->dict:
    """Read native mate definitions/errors and component constraint/remaining-DOF outputs. Use sw_set_mate_position for native distance/angle drivers. Reports unsupported DOF data as unavailable, never guesses a count or manual drag behavior."""
    return call('assembly_status',locals())

@tool()
def sw_set_mate_position(document_id:str,state:str,mate_name:str,value:float)->dict:
    """Drive one exact native distance/angle mate and solve the connected assembly. mm for distance, degrees for angle. Limit mates keep their original bounds and reject out-of-range targets before native mutation. This is a CAD pose command, not physical motion/force control."""
    return call('set_mate_position',locals(),True)

@tool()
def sw_move_component(document_id:str,state:str,component_name:str,translation_mm:list[float]|None=None,axis_world:list[float]|None=None,angle_deg:float=0.,pivot_mm:list[float]|None=None)->dict:
    """Attempt one incremental native mate-solved move; no Transform2 override. Read back the whole assembly and verify rigid/rotation-locked connections. Return requested versus achieved transforms, including rejected/projected targets. For limited joints drive the stored pose with sw_set_mate_position. No dynamics, contact or force claim."""
    return call('move_component',locals(),True)

@tool(read=True)
def sw_check_interference(document_id:str)->dict:
    """Compute native solid interference at the current assembly pose, with volumes and exact component names. No swept-motion, clearance or FEA claim."""
    return call('check_interference',locals())

@tool(read=True)
def sw_audit_assembly(document_id:str,clearance_pairs:list[dict]|None=None)->dict:
    """Current-pose inspection, no geometry edit or save: active mate errors, fixed-base reference connectivity, native limit margins and ALL solid overlaps. Optionally measure 0..16 explicit {component_a,component_b,minimum_mm} pairs using native ClosestDistance in assembly space. Returns PASS/REVIEW/FAIL/INCOMPLETE with exact names and measurements. No automatic repairs/overlap exemptions, inferred DOF counts, pin axial-engagement certification or motion sweep. Read-only handles supported. Fail on geometry-state drift; separately report native unsaved-flag changes without saving, resetting flags or discarding edits."""
    return call('audit_assembly',locals())

@tool(read=True)
def sw_mass_properties(document_id:str)->dict:
    """Read native SI mass, COM and inertia, with per-part material identity and override flags. Unassigned/default materials are explicitly unverified; never infer actual hardware mass from a placeholder."""
    return call('mass_properties',locals())

@tool(read=True)
def sw_materials(query:str='',maximum:int=80)->dict:
    """List matching materials from installed SOLIDWORKS .sldmat databases. Does not invent or assign a density."""
    return call('materials',locals())

@tool()
def sw_set_material(document_id:str,state:str,database_path:str,material_name:str)->dict:
    """Assign a named material from an installed .sldmat database to an editable part, read back identity and native mass. Appearance color alone is not material assignment."""
    return call('set_material',locals(),True)

@tool(read=True)
def sw_api_lookup(interface:str,member_name:str='')->dict:
    """Read real member/parameter names from the installed official 2025 type library without registering it."""
    return call('api_lookup',locals())

@tool()
def sw_add_components(document_id:str,state:str,components:list[dict])->dict:
    """Place 1..128 native parts in an EMPTY assembly. Each row: {path, transform:16 native numbers, fixed:bool}; SI translation, proper rigid rotations only. Verify every inserted reference and pose. Placement alone does not establish joints."""
    return call('add_components',locals(),True)

@tool()
def sw_connect_rigid_group(document_id:str,state:str,anchor_component:str,members:list[str],name_prefix:str='rigid')->dict:
    """Float 1..64 previously unmated members and connect them to one anchor using native lock mates. Preserve relative poses; verify every new mate and the final assembly. Does not ground the group anchor. Failure reports a partial edit and completed mates; never blindly retry."""
    return call('connect_rigid_group',locals(),True)

@tool()
def sw_create_joint(document_id:str,state:str,kind:Literal['revolute','prismatic','spherical'],name:str,axis_a:dict|None=None,axis_b:dict|None=None,plane_pairs:list[dict]|None=None,position:dict|None=None)->dict:
    """Explicit joint templates. Revolute: two cylinder references, one axial plane pair, optional angle position bounds. Prismatic: two orthogonal guide plane pairs, optional distance position bounds. Spherical: two sphere references only. References are fresh {component,face_id/plane_name}. plane_pairs rows {a,b,distance_mm?}; position {a,b,value,minimum,maximum}, mm/deg. Partial failures are reported, not automatically undone or retried."""
    return call('create_joint',locals(),True)

@tool()
def sw_set_mate_positions(document_id:str,state:str,positions:list[dict])->dict:
    """Drive 1..16 native positions together. Each row {mate_name,value}; mm/deg. Validate ALL bounds before writing, preserve native limits, rebuild and verify connected rigid groups. Native failures may leave partial edits; no automatic rollback or retry."""
    return call('set_mate_positions',locals(),True)

@tool()
def sw_set_dimensions(document_id:str,state:str,dimensions:list[dict])->dict:
    """Change 1..16 exact existing dimensions of one explicitly editable part, then rebuild and read back. Each row {dimension_name,value_si}; metres/radians. Validate the whole request before writing; no arbitrary parameter paths or rollback claim."""
    return call('set_dimensions',locals(),True)

@tool()
def sw_scan_motion(document_id:str,state:str,trajectory:list[list[dict]],restore_start:bool=True)->dict:
    """Sample 1..8 CAD poses, each a list of {mate_name,value} with the same driver names. Validate all bounds before starting; solve connected mates and inspect native interference at every sample. Optionally restore original driver values on success only. Source-part dimensions stay unchanged. Not continuous collision detection, physical simulation or automatic failure rollback."""
    return call('scan_motion',locals(),True)

@tool()
def sw_set_mate_suppressed(document_id:str,state:str,mate_name:str,suppressed:bool)->dict:
    """Suppress/unsuppress one exact native mate in the current configuration and verify active constraint validity. Retain the feature for inspection; never suppress arbitrary features or dependents. A failed unsuppress may leave a partial constraint change."""
    return call('set_mate_suppressed',locals(),True)

@tool()
def sw_organize_assembly(document_id:str,state:str,groups:list[dict],collapse:bool=True)->dict:
    """Organize ALL components into 1..16 descriptive native FeatureManager folders. Each row {name,components:[exact names]}; no duplicates, omissions or pre-existing folders. Collapse by default. Verify identical component geometry/poses/paths/fixed states and mates. No merging, suppression, hierarchy or file changes."""
    return call('organize_assembly',locals(),True)

@tool()
def sw_package_assembly(document_id:str,state:str,destination:str,names:list[dict],include_unsaved_assembly:bool=False)->dict:
    """Reference-aware copy with official SaveAs3 / AdvancedSaveAsOptions, SaveAllAsCopy. Supply every {source_path,file_name,subfolder?}; unique ASCII identifiers, matching extensions; optional single-level Parts folder. Destination must be empty. include_unsaved_assembly=True explicitly copies the current unsaved assembly state without saving/discarding the source; all parts must be saved. Verify source hashes, state and dirty flag unchanged. Reopen and verify copied references/poses/mates/STL."""
    return call('package_assembly',locals(),True)

@tool()
def sw_set_mate_flips(document_id:str,state:str,flips:list[dict])->dict:
    """Change native distance/angle mate sides together. Rows {mate_name,flipped:bool}; active flippable native mates only. Preserve magnitudes/bounds and verify connected rigid groups. Read back actual mirrored positions; native failure may leave partial side changes."""
    return call('set_mate_flips',locals(),True)

@tool()
def sw_set_assembly_pose(document_id:str,state:str,positions:list[dict],part_dimensions:list[dict])->dict:
    """Update assembly drivers AND referenced flexible-display part dimensions in ONE complete pose call. positions rows {mate_name,value}; part_dimensions rows {document_id,state,dimensions:[{dimension_name,value_si}]}. Prevalidate all references/values, freeze displays, solve/rebuild/read back, then refresh. Ordinary errors attempt bounded captured-parameter restoration; timeouts require inspection. Never chain separate pose/length calls for a flexible muscle preview."""
    return call('set_assembly_pose',locals(),True)

@tool()
def sw_close_reference_views(document_id:str,state:str,components:list[str])->dict:
    """Release windows for 1..80 exact saved top-level part components of an explicit parent assembly. Keep reference model data loaded; verify all parent components/mates and unsaved flag unchanged. Skip unsaved parts; refuse hidden unsaved documents. This is window/resource cleanup, not deleting, suppressing, unloading or saving parts. Inspect returned state before another edit."""
    return call('close_reference_views',locals(),True)


_delivery_checks = None


def _get_delivery_checks():
    global _delivery_checks
    if _delivery_checks is None:
        output = os.environ.get("SWLOCAL_OUTPUT", str(Path(__file__).resolve().parents[1] / "outputs"))
        _delivery_checks = DeliveryChecks(output)
    return _delivery_checks


@tool(read=True)
async def sw_find_tools(query: str, limit: int = 8) -> dict:
    """Find registered SOLIDWORKS tools by Chinese or English CAD keywords. Returns actual names and short descriptions. Does not run tools."""
    try:
        return {"matches": find_tools(await mcp.list_tools(), query, limit)}
    except ValueError as error:
        raise ToolError(str(error)) from error


@tool(read=True)
def sw_delivery_baseline(paths: list[str]) -> dict:
    """Before exporting, record content hashes or absence of 1..256 explicit expected STEP/STL/SLDPRT/SLDASM paths under the configured output root. Paths can be relative to that root. Keep the returned baseline_id within this MCP process."""
    try:
        return _get_delivery_checks().capture(paths)
    except (OSError, ValueError) as error:
        raise ToolError(str(error)) from error


@tool(read=True)
def sw_verify_delivery(baseline_id: str) -> dict:
    """After exporting, compare every declared output with sw_delivery_baseline. Only nonempty new or content-changed files pass. Report unchanged, missing and empty outputs as needs_review. Hash evidence does not prove CAD validity or who wrote a file."""
    try:
        return _get_delivery_checks().verify(baseline_id)
    except (OSError, ValueError) as error:
        raise ToolError(str(error)) from error


_assembly_journal = None
_package_evidence = {}


def _journal():
    global _assembly_journal
    if _assembly_journal is None:
        _assembly_journal = AssemblyJournal(os.environ.get("SWLOCAL_TEMP") or Path(tempfile.gettempdir()) / "solidworks-mcp")
    return _assembly_journal


@tool(read=True)
def sw_compare_assemblies(before_document_id: str, after_document_id: str,
                          component_map: dict[str, str] | None = None, mate_map: dict[str, str] | None = None,
                          dimension_components: list[str] | None = None, position_mm: float = .01,
                          angle_deg: float = .01, include_mass: bool = True) -> dict:
    """Compare two explicit assemblies. By default match exact names; use one-to-one old-to-new mappings for renamed items. Reports pose, limit, mate, component and native mass changes. Optional dimension_components are matched baseline names (max 16)."""
    return call("compare_assemblies", locals())


@tool(read=True)
def sw_capture_joint_recipe(document_id: str, state: str, kind: Literal["revolute", "prismatic"], name: str,
                            component_a: str, component_b: str, guides: list[dict],
                            axis_faces: list[int] | None = None, position: dict | None = None) -> dict:
    """Capture a reusable joint JSON recipe from current geometry. Guides are {plane_a,plane_b,distance_mm?}; revolute also requires two fresh cylinder face IDs. Optional position is {plane_a,plane_b,value,minimum,maximum}. Stores native face/plane signatures, not reusable face IDs."""
    return call("capture_joint_recipe", locals())


@tool()
def sw_apply_joint_recipe(document_id: str, state: str, recipe: dict, component_a: str,
                          component_b: str, preview: bool = True) -> dict:
    """Preview or apply a joint recipe on an explicit assembly copy or new assembly. Resolves unique fresh references; rejects changed geometry. preview=False opts into native mate creation. Inspect after a failed write."""
    return call("apply_joint_recipe", locals(), write=not preview)


@tool()
def sw_run_assembly_steps(document_id: str, state: str, label: str, steps: list[dict]) -> dict:
    """Run and durably journal up to 16 explicit {action,parameters} rows on one assembly. Supported: set_mate_positions, scan_motion, audit_assembly, apply_joint_recipe. Stops on first failure; no automatic replay. Find the task ID via sw_assembly_task_status if the client times out."""
    try:
        result = _journal().run(call, document_id, state, steps, label, ToolError)
    except (OSError, ValueError) as error:
        raise ToolError(str(error)) from error
    if result["status"] == "failed":
        step = result["steps"][-1]
        raise ToolError(json.dumps({"code": "ASSEMBLY_TASK_FAILED", "task_id": result["task_id"],
                                    "completed_steps": result["completed_steps"], "failed_step": step["index"],
                                    "native_code": step["error_code"], "outcome_unknown": step["outcome_unknown"],
                                    "retry_automatically": False}))
    return result


@tool(read=True)
def sw_assembly_task_status(task_id: str | None = None, limit: int = 10) -> dict:
    """Read one saved task and step evidence or list recent tasks. Durable across MCP reconnects with the same runtime root. A task abandoned by another process needs inspection before further edits."""
    try:
        return _journal().get(task_id) if task_id is not None else {"tasks": _journal().recent(limit)}
    except (OSError, ValueError) as error:
        raise ToolError(str(error)) from error


@tool()
def sw_verify_package_references(assembly_path: str, expected_parts: list[str]) -> dict:
    """Open a saved, closed output assembly as read-only and verify resolved top-level part references against explicit package-relative files. Leaves the inspected assembly open. No documents are closed or saved."""
    checks = _get_delivery_checks()
    try:
        assembly, expected = package_paths(checks.root, assembly_path, expected_parts)
        paths = [str(assembly), *(str(p) for p in sorted(expected))]
        previous = checks.current(paths)
        result = call("verify_package_references", {"assembly_path": str(assembly), "expected_parts": expected_parts})
        latest = checks.current(paths)
        if previous != latest:
            raise ValueError("Package files changed during the reference inspection")
    except (OSError, ValueError) as error:
        raise ToolError(str(error)) from error
    _package_evidence[result["document_id"]] = {**result, "files": latest}
    if len(_package_evidence) > 32:
        _package_evidence.pop(next(iter(_package_evidence)))
    return result


@tool()
def sw_write_acceptance_report(before_document_id: str, after_document_id: str, path: str,
                               title: str = "SOLIDWORKS 装配验收", component_map: dict[str, str] | None = None,
                               mate_map: dict[str, str] | None = None, dimension_components: list[str] | None = None,
                               clearance_pairs: list[dict] | None = None, delivery_baseline_id: str | None = None,
                               task_id: str | None = None) -> dict:
    """Write a standalone HTML report from fresh native revision and pose checks. Optional file baseline, journal task and verified reopen evidence are clearly scoped. Uses a new HTML path under the output root; never overwrites a report."""
    if not title.strip() or len(title) > 160:
        raise ToolError("Use a nonempty title of at most 160 characters")
    comparison = call("compare_assemblies", {
        "before_document_id": before_document_id, "after_document_id": after_document_id,
        "component_map": component_map, "mate_map": mate_map, "dimension_components": dimension_components,
    })
    audit = call("audit_assembly", {"document_id": after_document_id, "clearance_pairs": clearance_pairs})
    latest_before = call("snapshot", {"document_id": before_document_id})
    if audit["state"] != comparison["after"]["state"] or latest_before["state"] != comparison["before"]["state"]:
        raise ToolError("Assembly changed while collecting report evidence. Read fresh geometry and retry the report.")
    try:
        checks = _get_delivery_checks()
        delivery = checks.verify(delivery_baseline_id) if delivery_baseline_id is not None else None
        task = _journal().get(task_id) if task_id is not None else None
        reference = _package_evidence.get(after_document_id)
        if reference and (reference["state"] != audit["state"] or
                          checks.current(list(reference["files"])) != reference["files"]):
            reference = {**reference, "status": "STALE"}
        if reference and reference["status"] == "PASS" and delivery and not {
            row["path"].casefold() for row in delivery["files"]
        }.issuperset(path.casefold() for path in reference["files"]):
            delivery = {**delivery, "status": "package_files_not_all_declared"}
        if call("snapshot", {"document_id": after_document_id})["state"] != audit["state"]:
            raise ValueError("Candidate changed after audit; collect fresh evidence before reporting")
        status, html = render_report(title, comparison, audit, delivery, reference, task)
        target = write_report(checks.root, path, html)
    except (OSError, ValueError) as error:
        raise ToolError(str(error)) from error
    return {"report_path": target, "status": status, "candidate_state": audit["state"],
            "scope": "Declared checks only. See the report for any unchecked or unbound evidence."}


@mcp.resource('solidworks-mcp://guide')
def guide()->str:
    return 'Connect, list/create/open an explicit document, inspect state, edit serially, inspect again. Use fresh part-local face IDs or exact reference-plane names. Ground only the base; connect rigid pieces with lock mates, revolute joints with concentric and axial-location mates, sliders with rotation-locked concentric or two independent planar constraints. Add native distance/angle limits. Drive limited joints with sw_set_mate_position or sw_set_mate_positions; generic dragging can solve back to the stored limit dimension. Read native errors, verify actual connected-part poses, and save/reopen; never replace joints with fixed placements. Organize assembly trees into descriptive module folders with sw_organize_assembly and collapse them. Use stable project/module/serial identifiers plus concise English file descriptions, distinct L/R for mirrored parts, and consistent STL stems. Keep revision in metadata/release folders. Use sw_package_assembly for reference-aware renamed copies; reopen and verify references, poses, mates and exports. Never merge, suppress or delete functional parts merely to shorten the tree. A whole-assembly STL is only an assembly preview. For separate-part/printing delivery, export distinct native parts with a quantity/category manifest, exclude explicitly nonprinting placeholders, and verify source hashes and geometry states. Report blocked or partial exports honestly. Native GetRemainingDOFs returns an availability enum, not a count. Limits use nonnegative native reference distances/angles; signed joint ranges require an explicit offset datum. For flexible-display muscle previews use sw_set_assembly_pose to update drivers and dimensions together; never leave a half-updated pose. STL exports use millimetres, binary encoding, retained origin and one assembly file, with previous export settings restored. Kinematics and pose interference are not dynamics or FEA. No arbitrary code or macros. Consult VERIFICATION.md for tested scope.'

def main():
    mcp.run(transport='stdio')

if __name__=='__main__': main()
