# MCP tools — v1.4.0

93 tools. Native inputs must be trusted; API and GUI sessions are distinct.

## apply_model_edits

Preview or atomically commit 1..50 supported model parameter edits. Requires observed revision; failures leave live model unchanged. Commit creates a durable before-checkpoint/journal and one undo step. GUI sync occurs after API commit and is reported separately.

[Implementation](../src/opensim_mcp/extensions.py#L55)

## assemble_wearable_model

Attach trusted CAD meshes to a human-model copy. Each physical link explicitly supplies SI mass/COM/inertia and Weld/Pin/Slider joint; optional one-coordinate linear coupling. Explicit transform or >=3 corresponding CAD/body-frame landmarks. Mesh units mandatory. Visual-only mode adds offset frames without mass. Outputs portable model/meshes; does not guess strap/contact forces or alter API/source. Optional GUI open uses multi-session revision guard.

[Implementation](../src/opensim_mcp/v11_tools.py#L37)

## assess_actuator_usage

Report actuator force/moment RMS and peaks; optional ratios to explicit ID/reference columns on coincident samples. Definitions: name, role, unit, force_column, optional reference_column. Zero reference is not assessed; no implicit acceptance threshold.

[Implementation](../src/opensim_mcp/extensions.py#L114)

## assess_ik_quality

Calculate native marker-position RMS/max residuals and per-marker errors. Default requires coincident samples; explicitly select interpolation=linear for different time grids (no extrapolation). Returns sampling/interpolation details and optional caller threshold.

[Implementation](../src/opensim_mcp/extensions.py#L298)

## assess_moco_mesh_study

Assess a mesh study with caller RMS limits covering every named state and control exactly. Reject incomplete/extra columns and nonfinite metrics; report failed columns and objective check separately. Numeric assessment, not full mathematical/physiological validation.

[Implementation](../src/opensim_mcp/v11_tools.py#L32)

## attach_visualization_signals

Bind MATLAB/CSV/MOT/STO signals to an exported native animation.json. Requires explicit time column, s/ms units, offset, interpolation and gap limit; channel labels/units and optional known body/frame/muscle/coordinate/marker mapping. Reject extrapolation, missing data and stale optional physics signatures. Creates an offline 3D/curve workspace, copies numeric sources and records hashes. No native model change or cross-software live synchronization.

[Implementation](../src/opensim_mcp/visual_tools.py#L13)

## audit_moco_trajectory

Evaluate every exported state/control node (<=1000) in an explicit native model with the same external loads/tendon assumption. Report actual actuator outputs with N/Nm units, muscle activations, native control bounds and position/velocity constraint errors. Full states/controls and coincident nodes mandatory; not a forward replay, between-node defect or physiological proof.

[Implementation](../src/opensim_mcp/v11_tools.py#L15)

## cancel_job

Cancel a queued/running isolated workflow, stop its Windows process tree and prevent result publication. cancelled=true is returned only after confirmed termination. If completion committed first, returns completed.

[Implementation](../src/opensim_mcp/extensions.py#L162)

## capture_gui_image

Capture only the OpenSim Swing window and return PNG content. Hardware-accelerated 3D/browser surfaces can be blank; render_model provides native pose geometry independently.

[Implementation](../src/opensim_mcp/extensions.py#L251)

## check_opensim_code

Check Python syntax and direct OpenSim API symbol existence, returning line/column diagnostics. Never executes the supplied code. Does not prove types, model validity or solver feasibility.

[Implementation](../src/opensim_mcp/extensions.py#L218)

## check_version_compatibility

Probe installed native API/Python/NumPy and Moco/MarkerPlacer capabilities against tested Windows profiles. Reports unsupported/unknown combinations distinctly; import/symbol checks do not prove a solver run or GUI compatibility.

[Implementation](../src/opensim_mcp/extensions.py#L34)

## close_api_session

Stop the API worker and discard unsaved in-memory model/variables. Saved result files remain.

[Implementation](../src/opensim_mcp/server.py#L120)

## compare_wearable_inverse_dynamics

Compare baseline and verified welded-device ID on identical kinematics/loads/filter; quantify added mass demand. Optional ideal assist table needs every ID sample and explicit coordinate/column/N-or-Nm mapping. Remaining demand = combined ID minus assist. Reject changed models or articulated links needing study-specific force projection. Does not infer muscle/strap/contact forces or clinical benefit.

[Implementation](../src/opensim_mcp/v11_tools.py#L8)

## compare_wearable_muscle_forces

Compare verified welded added device masses using identical motion, loads, muscle parameters, explicit actuators and SO settings. Validates assembly/source hashes. Reports baseline/wearable muscle forces and peak/mean/RMS/impulse differences with numeric quality. No active motor assistance, altered gait, strap/contact-pressure or clinical benefit inference.

[Implementation](../src/opensim_mcp/exoskeleton_tools.py#L14)

## configure_model_actuators

Add explicit CoordinateActuators to a new model. Each definition needs name, coordinate, reserve/residual role, N/Nm unit, optimal_force, min_control and max_control. Reject existing coordinate actuators and locked/dependent coordinates; native readback validates units.

[Implementation](../src/opensim_mcp/extensions.py#L109)

## connect_gui

Prepare/probe the local GUI bridge. The optional startup plugin attaches on each GUI launch; manual Scripts > Run... is the fallback. Does not launch or restart OpenSim.

[Implementation](../src/opensim_mcp/server.py#L126)

## create_biomechanics_project

Create a strict reviewable scale/MarkerPlacer/IK/fit/ID/MuscleAnalysis/SO/JointReaction project, optionally RRA and explicit reserves. No guessed body scaling, external loads, actuator roles or physiological thresholds; validate_project then run_project explicitly.

[Implementation](../src/opensim_mcp/v1_tools.py#L51)

## create_checkpoint

Save API model definition, coordinate pose, time, runtime version and hash under results. Does not serialize arbitrary Python variables or external side effects.

[Implementation](../src/opensim_mcp/extensions.py#L172)

## create_project

Validate and save a project under results, using existing absolute allowlisted inputs. No source file is overwritten.

[Implementation](../src/opensim_mcp/extensions.py#L124)

## create_visualization_workbench

Create a simple offline one/two-scene 3D comparison workspace. Each scene requires animation.json path, label and explicit time_offset_s. Shared overlap timeline uses nearest native samples only within max_time_delta_s; unmatched poses are hidden. Supports linked cameras/selection, distance/three-point angle measures, curves/differences, visibility and portable view-state save/restore. Optional one-to-one left/right component mappings and exact-input-bound saved state. No automatic registration, live sync, anatomical joint-angle or surface clearance inference.

[Implementation](../src/opensim_mcp/visual_tools.py#L7)

## diagnose_opensim_error

Locate traceback files/lines and attach targeted input/runtime/solver hints. Text is analyzed as data; no code is executed.

[Implementation](../src/opensim_mcp/extensions.py#L229)

## disconnect_gui

Stop the bridge timer inside OpenSim. Leaves GUI, models and saved files open.

[Implementation](../src/opensim_mcp/server.py#L164)

## edit_model_topology

Preview/commit bounded body, Pin/Slider/Weld joint, marker and coordinate-actuator additions; whole set-member removal/rename and supported joint reconnection. Validates a candidate in another native process, preserves shared native states, commits as one undo step with full-state checkpoint/journal. Defaults to preview.

[Implementation](../src/opensim_mcp/v1_tools.py#L24)

## ensure_gui_connection

Observe/wait for the auto bridge, optionally launch the configured GUI if none is running. Never closes another GUI or merges models. Reports actual bridge/core version and startup failure; durable identity permits queue recreation.

[Implementation](../src/opensim_mcp/v1_tools.py#L38)

## estimate_muscle_volumes

Record explicitly supplied muscle volumes in cm3 with source, or estimate V=Fmax*optimal_fiber_length/specific_tension using explicit Pa assumption. No default specific tension or anatomy guessed from paths. Reports per-muscle provenance and model physics identity for viewer binding. Does not independently verify measurements or reconstruct anatomical shape.

[Implementation](../src/opensim_mcp/exoskeleton_tools.py#L22)

## evaluate_opensim_code

Execute trusted arbitrary Python in the persistent API worker with osim, np, model and state. Requires ENABLE_SCRIPTS=1; has full user permissions. Assign result for structured output. Failure returns status=failed and traceback; partial side effects persist. Timeout kills the worker and loses variables.

[Implementation](../src/opensim_mcp/server.py#L110)

## export_model_animation

Offline interactive 3D player: surfaces, native muscle paths with visibility/width controls, timeline, orbit/zoom, joint curves, comparison motion and marker-distance coloring. Native transforms and active/wrapped muscle paths are sampled on a model copy. Optional muscle result reports add force/activation coloring, picking, paired curves and CSV with physics/motion identity checks; volume reports preserve provenance. Muscle thickness is illustrative. Explicit linear data interpolation never extrapolates. Function-based paths without geometry are reported as unavailable. Reads only already-approved OBJ/STL/self-contained VTP and supported primitives; no textures/network. Sharing includes motion/model data. Visual sampling is not full-trial quality assessment.

[Implementation](../src/opensim_mcp/v1_tools.py#L8)

## export_model_scene

Export actual API native 3D body-frame/marker coordinates in meters, standalone SVG orthogonal views and a self-contained HTML viewer. No surface meshes or animation; pull GUI state explicitly to export its pose.

[Implementation](../src/opensim_mcp/extensions.py#L78)

## export_project_bundle

Bundle explicit project input data and configuration with hashes/runtime dependency metadata. Model XML is normalized to the self-contained native profile, display geometry removed. No credentials, scripts, meshes or runtimes. Includes input data: review sharing rights before publishing.

[Implementation](../src/opensim_mcp/extensions.py#L40)

## get_api_documentation

Discover actual installed OpenSim symbols or inspect public Class.method docs/member names without executing user code. Version-specific, bounded output.

[Implementation](../src/opensim_mcp/extensions.py#L203)

## get_api_session

Start/probe the separately configured persistent OpenSim Python API worker. Does not attach to GUI.

[Implementation](../src/opensim_mcp/server.py#L82)

## get_component_details

Read a native component's public properties and socket connectee paths by absolute model path.

[Implementation](../src/opensim_mcp/extensions.py#L213)

## get_current_model

Read the actual current model, signature and pose in the connected OpenSim GUI. Does not read the separate API worker's model.

[Implementation](../src/opensim_mcp/server.py#L133)

## get_environment

Inspect local paths and probe the selected API/CLI backend version; does not solve IK.

[Implementation](../src/opensim_mcp/server.py#L51)

## get_gui_selection

Read the actual OpenSim Navigator selection, including native object/component identity when the selected node exposes it.

[Implementation](../src/opensim_mcp/extensions.py#L257)

## get_job_status

Read durable job state, actual workflow phase, native log tail and completed result. Solver completion percentage is unknown. Interrupted server runs are distinguished from completion.

[Implementation](../src/opensim_mcp/extensions.py#L157)

## get_model_component

Read properties from a body, coordinate, marker or muscle in the current API model.

[Implementation](../src/opensim_mcp/server.py#L92)

## get_model_state

Read bounded named native state values (positions, speeds, activations and other available states) without executing Python or changing revisions/undo. Paginate or select exact paths; native units apply.

[Implementation](../src/opensim_mcp/v1_tools.py#L18)

## get_project_run

Read persistent stage/cache history, measured quantities and quality-report location, including failed/interrupted runs.

[Implementation](../src/opensim_mcp/extensions.py#L139)

## get_project_schema

Return the strict versioned portable project JSON schema. References track inputs and earlier stage outputs; a project cannot grant roots or select executables.

[Implementation](../src/opensim_mcp/extensions.py#L119)

## get_recovery_status

List durable model/native-state recovery snapshots across server restarts, with owner identities. Recovery requires an explicit selected snapshot; no cross-chat model is restored automatically.

[Implementation](../src/opensim_mcp/v1_tools.py#L43)

## import_c3d_trial

Convert trusted C3D to meters TRC and N/m/Nm loads. Requires explicit proper rotation; plates need explicit index/body/name and force sign. Only source Z-up force filtering, no guessed side/sign or gap filling. COP free moment is used, not the moment about platform origin.

[Implementation](../src/opensim_mcp/v1_tools.py#L91)

## import_project_bundle

Verify and import a portable project to a fresh result folder, checking data/units without executing native models or hooks. Never overwrites inputs or grants additional roots.

[Implementation](../src/opensim_mcp/extensions.py#L50)

## inspect_c3d_file

Inspect trusted C3D markers, rates, units, gaps and force-platform count in an isolated native parser. Does not infer axes/sign or convert data.

[Implementation](../src/opensim_mcp/v1_tools.py#L86)

## inspect_gait_cycles

Find complete same-foot/platform force-event cycles using an explicitly chosen upward force column in N, sign and hysteresis thresholds. Initial contact without observed onset is not a heel strike. First meeting source sample, no interpolation or guessed foot mapping; verify kinematic coverage.

[Implementation](../src/opensim_mcp/v11_tools.py#L26)

## inspect_model

Safely parse an allowed .osim XML file without loading OpenSim. Counts/names are static, not native validity checks.

[Implementation](../src/opensim_mcp/server.py#L64)

## inspect_visualization_workspace

Verify a visualization.json workspace, bounded local asset paths and every file hash; list component identifiers and signal provenance. No scripts, CAD or native models are executed; integrity does not establish source trust or physical equivalence.

[Implementation](../src/opensim_mcp/visual_tools.py#L19)

## list_checkpoints

List persistent model/pose savepoints from newest to oldest.

[Implementation](../src/opensim_mcp/extensions.py#L177)

## list_edit_transactions

Read durable batch edit journal entries, including recovery checkpoints.

[Implementation](../src/opensim_mcp/extensions.py#L64)

## list_jobs

Read durable analysis history across MCP restarts; optional state filter and newest-first bounded list.

[Implementation](../src/opensim_mcp/extensions.py#L167)

## list_model_components

List actual native model component paths/classes with filtering and pagination.

[Implementation](../src/opensim_mcp/extensions.py#L208)

## load_model

Load and natively initialize a trusted self-contained model in the API session, retaining other script variables. GUI is separate.

[Implementation](../src/opensim_mcp/server.py#L87)

## load_motion_in_gui

Load an allowed .mot into GUI for the actual current model.

[Implementation](../src/opensim_mcp/server.py#L143)

## open_model_in_gui

Open an allowed trusted original model in GUI, retaining visual geometry/dependencies. Previous GUI models are kept.

[Implementation](../src/opensim_mcp/server.py#L138)

## place_model_markers

Run native MarkerPlacer on an already scaled model, moving only named markers. Static TRC, IK weights and movement limits are explicit; optional manual coordinate targets use rad/m. Saves a new initialized model and one-frame static pose.

[Implementation](../src/opensim_mcp/extensions.py#L102)

## plot_motion_result

Create standalone PNG/SVG curves with explicit columns/units and return the actual PNG image to the MCP client. Large series use min/max decimation preserving spikes.

[Implementation](../src/opensim_mcp/extensions.py#L234)

## prepare_moco_model

Create a native-initialized Moco model copy with explicitly selected DeGrooteFregly2016 conversion, tendon/passive changes and named reserve/residual actuators. Reports each muscle class before/after. Physics change is explicit and requires renewed validation.

[Implementation](../src/opensim_mcp/v1_tools.py#L61)

## prepare_wearable_motion

Copy a complete human motion and add only device coordinates defined by verified explicit linear couplings, respecting rad/m and inDegrees. Reject missing independent motion, coupling mismatch, changed assembly model or range violations. No resampling/guessed motion.

[Implementation](../src/opensim_mcp/v11_tools.py#L47)

## read_image

Return an allowed bounded PNG as MCP image content, rather than a path-only response.

[Implementation](../src/opensim_mcp/extensions.py#L246)

## read_motion_result

Read an allowed .mot/.sto table. Return bounded preview, coordinate ranges, time coverage and units metadata.

[Implementation](../src/opensim_mcp/server.py#L69)

## reconfigure_gui_bridge

Preview/apply GUI bridge access roots from this server's existing configuration, preserving bridge identity and the current GUI model. Never accepts additional roots. Connected v1 bridges reload in place; legacy bridges require explicit allow_legacy_stop and a later GUI restart. Does not close the GUI.

[Implementation](../src/opensim_mcp/v1_tools.py#L33)

## recover_api_session

Restore a verified model plus all named native states/time after worker/server failure. Runtime must match. Replacing a live model requires discard_current=true and saves its recovery point. Does not replay scripts or restore GUI/files/Python variables.

[Implementation](../src/opensim_mcp/v1_tools.py#L47)

## redo_model_edit

Redo a structured parameter edit after undo, with optional revision guard and GUI push.

[Implementation](../src/opensim_mcp/extensions.py#L196)

## render_model

Render actual API pose as body-frame skeleton/markers and return a PNG plus SVG. Uses native state positions in meters; surface meshes are excluded. Pull GUI state first to render its pose.

[Implementation](../src/opensim_mcp/extensions.py#L240)

## resample_coordinate_motion

Create an explicitly requested uniform linear MOT/STO coordinate resampling, with source hash/window/rate. No extrapolation, smoothing, gap fill or angle unwrapping; retain inDegrees. Last full grid sample may precede requested end. Useful before filters that require uniform sampling.

[Implementation](../src/opensim_mcp/v11_tools.py#L21)

## restore_checkpoint

Verify hash/runtime and restore the API model/pose/time; preserve a recovery savepoint first. Cross-version restore requires explicit opt-in and native initialization. Python variables are outside the savepoint scope.

[Implementation](../src/opensim_mcp/extensions.py#L182)

## rollback_edit_transaction

Restore the pre-transaction model/pose/time checkpoint, requiring the currently observed revision; a recovery checkpoint preserves current state. Later model edits are replaced by this rollback.

[Implementation](../src/opensim_mcp/extensions.py#L69)

## run_inverse_dynamics

Run native ID. All coordinates are required, plus measured/modeled loads and force definitions, or explicit no_external_loads=true. Muscles are excluded; passive/contact model forces remain. Load units must be SI and coordinate inDegrees explicit.

[Implementation](../src/opensim_mcp/server.py#L169)

## run_inverse_kinematics

Run marker-based IK on trusted self-contained model/TRC files; save a fresh result folder. Null weights track all shared markers equally; explicit weights select only those markers. Times must be TRC sample times. Native execution is bounded, not OS-sandboxed.

[Implementation](../src/opensim_mcp/server.py#L74)

## run_joint_reaction

Run native JointReaction with explicit external loads/no-load assumption, selected joints and reporting body/frame. Models with actuators require a complete force table or explicit ignore_actuators. Returns finite force/moment tables and peak resultants.

[Implementation](../src/opensim_mcp/extensions.py#L279)

## run_moco

Fixed-time Moco/CasADi optimal control using complete explicit state/control bounds and a control-effort goal. Checks solver success, finite trajectory, endpoint/bound violations and optional doubled-mesh objective stability. Prefer submit_analysis for progress/cancellation.

[Implementation](../src/opensim_mcp/extensions.py#L289)

## run_moco_convergence

Run 2..4 native Track/Inverse refinements. Compare objective and interpolated full state/control trajectories; caller RMS thresholds decide assessed checks. Objective-only agreement is labeled separately. Prefer async moco_convergence for long solves.

[Implementation](../src/opensim_mcp/v1_tools.py#L67)

## run_moco_inverse

Structured MocoInverse with all-coordinate prescribed motion and explicit external-load assumption. Existing native actuator/control bounds apply; no automatic reserves. Optional tendon-compliance change is explicit. Reports convergence and sampled coordinate differences; prefer async moco_inverse.

[Implementation](../src/opensim_mcp/extensions.py#L93)

## run_moco_sensitivity

Native baseline and 1..5 explicit physical model/goal perturbations. Returns objective and trajectory differences. Model edits use the bounded body/coordinate/marker/muscle parameter profile; user API session is unchanged. Prefer async moco_sensitivity.

[Implementation](../src/opensim_mcp/v1_tools.py#L73)

## run_moco_track

Structured coordinate-reference MocoTrack. Requires complete rad/m state bounds, control bounds, all-coordinate motion with explicit inDegrees, and loads or no-load opt-in. Reports coordinate tracking RMS/peaks and feasibility; use moco_track via submit_analysis for cancellation.

[Implementation](../src/opensim_mcp/extensions.py#L83)

## run_muscle_analysis

Run native MuscleAnalysis and publish geometric/kinematic muscle outputs such as path lengths and moment arms. Does not infer muscle forces or activations.

[Implementation](../src/opensim_mcp/server.py#L177)

## run_muscle_force_study

Predict muscle tensions/activations with native SO and matched ID. Explicit reserve/residual profiles and all three numeric quality limits required. No automatic strengthening or actuator guessing. Reports per-muscle peaks/RMS/impulse, quality failures and original physics identity. Native optimizer failure aborts. Can return completed/needs_review; not physiological validation. Does not alter API/GUI.

[Implementation](../src/opensim_mcp/exoskeleton_tools.py#L7)

## run_opensim_script

Run a trusted allowed .py file in the persistent API session, with the same full-user-permissions boundary as evaluate_opensim_code.

[Implementation](../src/opensim_mcp/server.py#L115)

## run_project

Submit a staged asynchronous project. Reuse only hash-verified stages with matching inputs/settings/runtime/source. Completed stage checkpoints survive cancellation; incomplete stages do not. Poll/cancel through job tools.

[Implementation](../src/opensim_mcp/extensions.py#L134)

## run_residual_reduction

Native RRA using explicit torque/residual actuators/tasks. Restores original actuators in the adjusted model; optional COM adjustment and before/after ID residual assessment. No guessed roles, automatic mass recommendations or promised residual reduction. Use rra via submit_analysis for reliable cancellation.

[Implementation](../src/opensim_mcp/v1_tools.py#L78)

## run_static_optimization

Estimate muscle activation/force using native Static Optimization and the model's force set. External loads or explicit no-load assumption required. Does not automatically add reserves or certify physiological validity.

[Implementation](../src/opensim_mcp/server.py#L183)

## save_model

Save the current API model in a fresh result directory, never overwriting the input. Current pose is distinct from serialized coordinate defaults.

[Implementation](../src/opensim_mcp/server.py#L105)

## scale_model

Native manual/marker-pair model scaling with explicit target mass. Measurement entries specify body, axes and marker_pairs. Returns mass/distance checks and reopened output. Does not relocate virtual markers with MarkerPlacer.

[Implementation](../src/opensim_mcp/extensions.py#L272)

## select_gui_component

Select an existing component in OpenSim's Navigator and read back its actual selection.

[Implementation](../src/opensim_mcp/extensions.py#L262)

## set_gui_coordinate

Change an actual GUI pose coordinate and refresh display. Rotations use radians, translations meters. Optional signature rejects stale writes.

[Implementation](../src/opensim_mcp/server.py#L148)

## set_model_parameter

Edit a supported physical/default property on a native model copy, validate initialization, then commit to the API session. Optional GUI sync loads a new version; failure is reported separately after the API edit.

[Implementation](../src/opensim_mcp/server.py#L97)

## submit_analysis

Submit isolated asynchronous native workflows, including muscle_force_study, wearable_muscle_comparison and muscle_volumes. Parameters match the corresponding synchronous tool. Returns immediately; poll get_job_status or cancel_job. No arbitrary scripts or persistent API session mutation.

[Implementation](../src/opensim_mcp/extensions.py#L152)

## sync_gui_model

Explicit two-way sync. pull snapshots current GUI definition/pose into API; push saves API model and opens a new active GUI version. Models are not continuously auto-synchronized. Source files and previous GUI models remain.

[Implementation](../src/opensim_mcp/server.py#L154)

## undo_gui_pose

Undo the last bridge coordinate edit (up to twenty). Reject undo if GUI model/pose changed since that edit. Does not undo arbitrary GUI/file operations.

[Implementation](../src/opensim_mcp/extensions.py#L267)

## undo_model_edit

Undo the last structured API parameter edit, retaining up to ten edits in memory. Guard with expected_revision. Arbitrary scripts/model loads clear undo history; filesystem effects cannot be undone.

[Implementation](../src/opensim_mcp/extensions.py#L189)

## validate_project

Check strict project shape, ordered dependencies, asset types/units and input hashes without running native solvers.

[Implementation](../src/opensim_mcp/extensions.py#L129)

## validate_trial_inputs

Check model marker/coordinate coverage, units, external-load body/column mapping and common time window. No numerical solve or anatomical validation.

[Implementation](../src/opensim_mcp/v1_tools.py#L98)

## convert_body_mass_properties

Read-only, explicit CAD mass/COM/inertia conversion to central SI wearable body
parameters. Requires units, reference point, tensor/product sign convention,
proper source-to-target transform and source description. Rejects impossible
central inertias and unstable shifts. Does not change models, meshes or joints.

[Usage and exact fields](MASS_PROPERTIES.zh-CN.md)

## verify_project_bundle

Verify bounded ZIP inventory, paths, hash integrity and strict project graph without extraction or native execution. Hash integrity does not establish author trust or runtime compatibility.

[Implementation](../src/opensim_mcp/extensions.py#L45)
