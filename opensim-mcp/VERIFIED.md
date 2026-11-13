# Executed validation — local v1.4.1

2026-11-01, Windows 11 x64. 94 tools; **262 source tests passed**, including
20 new mass-property cases. A first restricted run had 260 passes and two
Windows process/stdout failures; the normal native Windows run passed all 262.
No new runtime dependency, GUI/workbench edit, installer build or public release.

New read-only conversion requires explicit kg/g, COM units, inertia units,
central/origin reference, tensor-entry/positive-product convention and proper
rotation/translation. Analytic point-cloud tests check independent mass sums,
parallel-axis subtraction, units, non-diagonal re-expression and provenance.
Existing wearable assembly rejects physically impossible finite-body inertias
before native work and reads all added bodies' mass/COM/six inertia values from
the natively saved/reopened model. Point/line singular profiles are unsupported.

Fresh real stdio MCP, with arbitrary scripts disabled, verified a rotated,
offset-COM 2 kg analytic brick: central inertia and sign readback matched;
native slider inverse-dynamics demand increased exactly **2 N** for 1 m/s²;
non-principal rotational kinetic energy was **0.02731065779119444 J**, versus
independent analytic **0.027310657791194442 J**. Impossible principal triangle
input was rejected. Mesh was illustrative, not matched to that brick's mass.

This is not a real exoskeleton/CAD material calibration, automatic mesh/joint
frame transformation, anatomy/contact model, assistance or metabolic validation.
User API/GUI/models/configuration and the public/private release split remain.
Evidence: [validation/windows11-v1.4.1-mass-properties.json](validation/windows11-v1.4.1-mass-properties.json).

# Executed validation — v1.4.0

2026-11-01, Windows 11 x64. 93 tools; 242 source tests passed. Native
two-scene MCP export/workbench/state restore and stale/tamper rejection passed.
Browser checks cover shared timeline/camera, direct mesh picking, linked selection
and visibility, exact 0.05 rad synthetic coordinate difference, distance/angle
checked independently against native transform values, CSV/state export and
reopening/restoring view state. Missing matches are hidden, old state identities
rejected, 390px layout has no horizontal overflow. Zero JavaScript exceptions.
Single official Arm26 muscle selection and original analytic force curves were
also inspected. Existing external-signal player regressions passed.

No dependency change, live synchronization, automatic model registration,
anatomical angle or mesh-clearance inference. Measurements use native markers
and frame origins. No new clean-Win11 VM or GUI lifecycle test is claimed.
Earlier public installer/private hosted CI ran on 2026-10-31, with 220 source
tests after distribution additions; earlier 215-test records below describe the
preceding scope. Hosted Windows Server CI is distinct from local Windows 11.

[Workbench guide](docs/WORKBENCH.zh-CN.md) · [Evidence](validation/windows11-v1.4.json)

# Executed validation — v1.3.0

Executed on 2026-10-31, Windows 11 x64. **92 MCP tools; 215 adapter tests passed**.
Fresh stdio server called both new tools with scripts disabled, exported a native
31-frame scene, checked exact source samples and rejected deliberately changed
workspace files. No runtime dependency changes.

MATLAB R2024b executed the timetable export helper (Code Analyzer: no issues).
Each upper/lower demonstration has four explicitly labeled synthetic channels,
121 source samples and 61 native pose frames. Browser tests checked continuous
and previous-value data, curve-to-pose picking, actual values, component mapping,
CSV/context downloads, playback and compatibility without external signals:
zero JavaScript exceptions. Screenshots were visually inspected.

With explicit user authorization, SolidWorks 2025 was launched and a new owned
40 x 20 x 10 mm solid created, saved natively and exported as STL. Exported bounds
confirmed millimetres; native OpenSim visual assemblies recovered exactly
0.04 x 0.02 x 0.01 m on official Arm26 and an original lower-limb copy. Official
upper-limb geometry is local-only and excluded from the public source release.

These are synthetic exchange and visual-placement regressions, not subject/device
fit, muscle-force or contact validation. The implementation uses offline files;
there is no automatic live CAD/Simulink synchronization. Existing GUI, native
dependency profile and unrelated Codex MCP configurations are preserved.
Hosted GitHub/clean-OS checks and a new GUI lifecycle run were not executed.

[Usage](docs/VISUALIZATION_INTEROP.zh-CN.md) · [Machine-readable evidence](validation/windows11-v1.3.json)

# Executed validation — v1.2.0

Executed on 2026-10-29, Windows 11 x64. The complete adapter suite passed **192 tests**. Native analytic regression recovered 20 N support and 26 N after adding 0.6 kg under 10 m/s2 gravity; volume conversion recovered 200 cm3. The former v1.1 GUI regression remains historical; no GUI change was made in v1.2.

The human muscle-force illustration uses the official adjusted Gait2354 model and provided RRA reference segment, explicitly resampled to 60 Hz over **0.750–1.233333 s, 30 frames**. Both conditions completed native SO with 54 muscles and 23 explicit reserve/residual actuators. Right MTP, left subtalar and left MTP reserve/ID peak ratios exceed the explicitly configured 10% limit in each case: **needs_review**, not a validated physiological result. Failed raw-marker full-cycle SO and poorly tracking new RRA were rejected. This segment is not a complete gait cycle.

Browser validation confirmed native sample values, separate force/activation color modes, muscle picking, paired curves, CSV download and playback. Estimated volumes use the explicitly assumed 300000 Pa specific tension and are not measured anatomy. Public source contains original analytic fixtures; separately installed official human data and local study results are excluded from the source archive. Native OpenSim profile remains 4.6 build 2; runtime dependency pins are unchanged.

# Executed validation — v1.1.0

Executed on 2026-10-29, Windows 11 x64 build 26200. **87 MCP tools**;
**175 adapter tests passed**, no failures/errors in the final complete suite.
Primary native profile remains official OpenSim 4.6 wheel build 2, CPython 3.12.13,
NumPy 2.5.4; observed core `4.6-2026-06-22-85aaf64`. GUI is retained official
4.6_beta with actual core 4.5.2, now bridge 1.1.0; no final-GUI claim.

| Executed check | Evidence and practical limit |
| --- | --- |
| Real MCP | All seven new structured tools called with scripts disabled; 87 tools/version 1.1.0; prior v1 native-state recovery/topology/undo/viewer regression passed |
| GUI concurrency | Two owned real GUI launches; independent processes observed/rejected stale writes, cross-session undo rejected; auto bridge, restart/stale heartbeat, identity recreation and configuration reload passed; user GUI preserved |
| Complete human cycle | Recomputed IK covers measured right-foot events 0.6183–1.8533 s (1.235 s); old 0.4–1.6 s reference alone did not cover it |
| RRA/ID | Full-cycle RRA restores 54 muscles; explicit 60 Hz resampling before filtering, same-window before/after ID completed; one matching duplicate terminal row in each native table recorded/removed, conflicts rejected |
| Muscle Moco | Two native complete-cycle solves at 0.04/0.02 s meshes, 204/433 iterations, objectives 50306.34995/48925.10035; objective change about 2.75%; 100 states/77 controls assessed |
| Mesh judgment | **needs_review**: 114 of 177 state/control columns exceed the explicit example RMS limits, and objective check fails; not full convergence or physiological acceptance |
| Native trajectory audit | All 125 fine-grid nodes, 77 actuator outputs/54 activations; max native position/velocity constraint errors 0, control-bound excess about 9.97e-9; node checks do not prove between-node dynamics accuracy |
| Analytic wearable | 0.5 kg CAD cuff increases matched slider ID by 0.5 N under 1 m/s²; explicit 0.25 N ideal assist leaves 1.25 N demand; consistent-drive weld reaction 0.5 N horizontal/4.903325 N vertical checked; Pin coupling/degree conversion passed |
| Human wearable | Official Gait2354 copy plus two original illustrative cuffs, 14 bodies, +0.6 kg; matched kinematics/real measured plates ID comparison completed. These are not the user's actual device parameters |
| Schematic demo | Original seven-body lower-limb fixture + two cuffs: 9 bodies/meshes, 121 frames; API model unchanged by export. Headless Edge rendered 23,391 geometry pixels, timeline/play-pause passed; screenshot inspected |
| Installation | Windows PowerShell 5.1 fresh Unicode/space directory: pinned two environments, MCP/IK and actual tiny Moco/IPOPT solve passed |
| Faults/offline | Cold offline install fails; warm offline reinstall/repair succeeds; missing IPOPT plugin detected before Codex registration; missing ezc3d detected and repaired offline; fake Codex config byte-identical |
| Upgrade/rollback | Actual v1.0 80-tool native server → v1.1 87-tool native server → v1.0 80-tool server, using isolated Codex config/results/temp; exact roots/script setting and latest unrelated config preserved |
| Existing behavior | Native profiles/tracking, projects/cache/resume/cancel, portable bundles/transactions, C3D/RRA/synthetic Moco, recovery/topology/viewer suites passed |
| Workflow/static checks | Both workflows actionlint 1.7.12 pass with custom runner labels, all PowerShell parsed; no hosted run claimed |

[Machine-readable evidence](validation/windows11-v1.1.json) includes measured
metrics, assumptions and limitations. Earlier records remain under validation
and docs/VERIFIED-v1.0.md. The final ZIP is independently extracted/tested and its
hash/audit recorded in the accompanying release-validation JSON.

Native SolidWorks export was **not** executed: its connected service already had
the eight-document budget occupied; no existing document was closed or modified.
Native CAD documents require separately trusted SolidWorks software/MCP exports.
The package tests use original meshes and explicitly specified physical inputs.
Actual user device/CAD and calibrated strap/contact physics were not provided.

The current OS is Windows Home; Windows Sandbox/Hyper-V were unavailable here.
The clean-Win11 VM script/runbook is provided but **clean-OS execution remains
unperformed**. Fresh-directory fault tests do not replace it. Hosted GitHub CI/
Release and self-hosted workflow execution are also unperformed (local delivery).

No participant model/trial inputs, complete trajectories, private config, native
environments or session state are bundled. Solver success, a zero node constraint
error or a wearable visual fit is not clinical/physiological validity.

[Machine-readable v1.2 evidence](validation/windows11-v1.2.json)
