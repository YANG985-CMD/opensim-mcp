# Changelog

## 1.4.1 — 2026-11-13

Adds one read-only `convert_body_mass_properties` tool: explicit mass/COM/inertia
units, central/origin reference, tensor/product sign convention and proper-frame
conversion. Rejects impossible central inertias and ill-conditioned shifts;
preserves source provenance without claiming CAD truth or changing geometry.
Wearable assembly validates all link inertias before native work and reads back
mass/COM/six inertia entries after native save/reopen. No GUI/workbench changes,
or active-assistance/metabolic validation. Published with the Windows 11
bytecode installer and release-specific validation evidence.

## 1.4.0 — 2026-11-01

93 tools. Adds an offline single/two-scene workbench with a shared overlap timeline,
explicit nearest-native matching tolerance and visible missing poses, linked
normalized cameras, mesh/muscle and component-list selection, visibility/opacity,
coordinate/signal/force/activation comparison, marker/frame-origin distance and
three-point angle measures, CSV provenance and exact-input-bound view-state JSON.
The interface keeps playback visible and folds secondary controls. Existing
player behavior and native runtime pins remain. No live synchronization or mesh
clearance/anatomical angle inference is introduced.


## 1.3.0 — 2026-10-31

92 tools. Adds generic numeric signal binding and portable workspace inspection,
independent of body region. Explicit time units/offset/interpolation/gap limits;
no extrapolation or inferred unit conversion. Preserves source samples separately
from native animation frames, supports component binding, curve-to-pose selection,
CSV/context export, input snapshots and file hashes. Includes a MATLAB timetable
export helper, actual stdio regression and CI entry. Runtime pins are unchanged.

Executed native MATLAB R2024b CSV/JSON export and SolidWorks 2025 creation/save/STL
export of a 40 x 20 x 10 mm test block. Checked units and native OpenSim placement
on official Arm26 and original lower-limb copies; browser controls and exact
numeric readback passed. Synthetic signals and visual-only CAD placement do not
validate device fit or forces. No live cross-software synchronization is claimed.


## 1.2.0 — 2026-10-29

90 tools. Adds explicit muscle-force studies, verified welded-device mass
comparisons and measurement/parameter-volume provenance. SO and ID use the same
immutable input snapshots and explicit reserve/residual profiles and limits.
Optimizer failures abort; completed results can remain needs_review.

The offline player binds forces and activations to native model physics and
the exact motion input, with optional explicit interpolation and no extrapolation.
Adds force/activation coloring, click selection, two-condition force curves,
volume source labels, CSV export and visible numeric-quality results.
All three workflows support durable asynchronous jobs and process-tree cancellation.
Native paths include moving/conditional and wrap surface samples with illustrative
width controls.
Adds analytic 20 N / 26 N added-mass and 200 cm3 volume regressions.
Human illustration uses a provided 0.750–1.233 s reference segment, not a full
cycle; three foot reserve checks fail in each case, reported as needs_review.
No active motor assistance, individualized muscle anatomy or contact-pressure
validation is claimed.

## 1.1.0 — 2026-10-29

87 tools. Adds complete same-foot force-event cycle detection, explicit linear
coordinate resampling, complete named Moco mesh assessment and native state/
control/actuator/constraint audits. Human native regression now spans one measured
cycle; actual mesh differences are reported as needs_review rather than accepted.

Adds CAD mesh-to-model assembly with explicit SI mass/central inertia, Weld/Pin/
Slider joints, CAD-frame joint center/axes, rigid landmark fitting and optional
linear coordinate couplings; motion preparation and matched welded-device ID
with explicit ideal assist. Includes original lower-limb/cuff demo and native
analytic mass/force checks. Native CAD conversion and calibrated contact/strap
physics are not bundled or inferred.

GUI adds crash-released cross-process locks, atomic observed-state guards and
session-owned undo. Adds wheel-local CasADi lookup, actual solver diagnostics,
warm offline repair and registration after native checks. RRA normalizes only
matching round-off duplicate native times with audit, and preserves full sample
precision in matched ID comparisons. Provides clean-Win11 execution entry point;
clean VM and hosted execution are explicitly not claimed.



## 1.0.0 — 2026-10-29

80 MCP tools. Adds full named native-state/time recovery across worker/server
failure; full-state checkpoints/undo; isolated candidate topology validation and
supported structural transactions; explicit GUI lifecycle/configuration recovery;
offline interactive WebGL primitive/OBJ/STL/VTP motion, comparison and marker-error
views. Pins Python 3.12, ezc3d 1.7.2 and vtk 9.7.1. Adds opt-in human RRA/muscle
Moco reproduction and self-hosted Win11 desktop workflow. Preserves configured
roots exactly during release activation. Local evidence and limits are recorded.

## 0.9.0 — 2026-10-29

73 tools. Adds explicit C3D/force-platform conversion and trial validation,
scale-to-muscle project templates, native RRA with original actuators restored,
explicit DGF muscle-model preparation, mesh comparisons and finite sensitivity.
Includes analytic force/IK fixtures and short-window official human regressions.

## 0.8.1 — 2026-10-29

Adds verified Windows source-release extraction, side-by-side installation,
Codex configuration activation and guarded rollback, preserving the old release.
Native installation/activation/rollback was exercised with a throwaway Codex config.


## 0.8.0 — 2026-10-29

65 MCP tools. Adds portable project export/verify/import with strict Windows ZIP
paths and a complete file hash inventory; supported parameter-edit transactions
with preview, revision checks, single-step undo, recovery checkpoints and durable
rollback journals; native 3D pose JSON with three orthogonal SVG/HTML views.

Adds one-click Windows 11 installation, dependency/source diagnostics, limited
pinned-environment repair and explicit runtime compatibility probing. Includes
hashed dependency locks, reviewed/pinned GitHub Actions, native regression steps,
source ZIP/SHA256 packaging and a gated tag-release job. Hosted execution requires
uploading to an actual repository and is not claimed as a local validation.

## 0.7.0 — 2026-10-28

Structured MocoTrack and MocoInverse profiles with explicit all-coordinate
references, loads/units, bounds and solver settings. Reports sampled feasibility
and tracking RMS. Tests include degree-to-radian conversion and a synthetic
muscle/external-force inverse problem.

## 0.6.0 — 2026-10-28

Static MarkerPlacer on already scaled models, explicitly selected movable markers
and movement limits; explicit reserve/residual CoordinateActuator profiles and
physical force/torque usage checks against named reference columns.

## 0.5.0 — 2026-10-28

Strict project manifests and staged native pipelines; input/runtime/code hashes,
verified cache/resume, partial completion journals and explicit quality reports
with self-contained HTML, Markdown, JSON and curves.

## 0.4.0 — 2026-10-28

Asynchronous jobs, progress, Windows process-tree cancellation and persistent
history; checkpoints/undo; API/diagnostic discovery; client-visible images; GUI
selection/capture/pose undo; scaling, JointReaction, Moco and IK fit assessment;
human force-plate, cross-version and GUI lifecycle regression scripts.

## 0.3.0

Independent API/GUI synchronization, startup-plugin GUI bridge, core native
analyses, trusted scripting and an isolated official OpenSim API environment.
