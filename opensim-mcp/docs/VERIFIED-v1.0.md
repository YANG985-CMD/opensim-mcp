# Executed validation — v1.0.0

Executed locally on **Windows 11 x64, build 26200**, on 2026-10-29.
The final fresh stdio server and actual Codex configuration expose **80 tools**.
**164 adapter tests passed**, zero failures/errors. Existing user Codex settings,
input roots and scripting preference were preserved.

Primary runtime: CPython 3.12.13, official opensim 4.6 wheel build 2, actual core
`4.6-2026-06-22-85aaf64`, NumPy 2.5.4. Main dependencies match the hashed locks,
including ezc3d 1.7.2 and vtk 9.7.1. GUI remains the official 4.6_beta package,
actual core `4.5.2-2026-02-17-1df1a24`; not a verified final 4.6 GUI.

| Executed check | Observed result |
| --- | --- |
| Final MCP | 80 tools/version 1.0.0; native-state reads, topology, viewer, undo/redo/rollback and MCP-restart recovery worked with arbitrary scripts disabled |
| Failure injection | Killed native worker and timed out script; restored position 0.03 m, speed 0.12 m/s, activation 0.37 and time 0.25 s with state error below 1e-12; Python sentinel not replayed; stale revision changed |
| Topology | Connected two-body preview/commit, full-state preservation, undo/redo, body/joint rename and persistent rollback passed; disconnected body rejected without losing live model |
| GUI lifecycle | Two owned launches auto-attached; stale heartbeat rejected; deleted queue config recreated with same identity; in-place root reload preserved model signature and GUI process |
| GUI MCP | Selection, capture images, pose/undo and explicit sync passed with 80 tools; existing user GUI was not edited or closed |
| Native viewer | 31 frames/two meshes; known native translation/rotation and 0.03 m marker comparison verified; API model/full state/revision unchanged |
| Edge browser | Public check_player.cjs / Playwright core 1.64.1: 24,603 mesh pixels, timeline, error colors, orbit/reset and play/pause passed; zero JS errors, screenshots visually inspected |
| C3D | Synthetic mm→m with explicit rotation/sign/platform mapping; analytic IK max error 1.39e-17 m, unfiltered ID=-5 N; 100 N vertical force and COP free moment checked |
| Muscle pipeline | Eight-stage scale/MarkerPlacer/IK/fit/ID/MuscleAnalysis/SO/JointReaction completed; only configured checks determine acceptance |
| RRA/Moco | Native RRA, same-window before/after ID, original muscle restoration, two-mesh synthetic MocoInverse and force-parameter sensitivity passed |
| Human core | Official installed Gait2354, 23 coordinates/54 muscles, measured plates; ID/IK and 4.6→4.3→4.6 save passed; 73-row compared ID maximum difference 0 N/Nm for this example |
| Human short studies | Public regression_human_studies.py passed: RRA requested 0.4–0.6 s, actual 0.4–0.599 s; 54 muscles restored; explicit DGF/reserve model and muscle MocoInverse 0.4–0.5 s with 0.015/0.0075 s meshes completed |
| Existing workflows | Native profiles, whitespace/degree reference tracking, project quality/cache/resume/cancellation, portable bundles and parameter transactions passed |
| Installation | Fresh source directory on Win11, Windows PowerShell 5.1, pinned server/API environments including C3D/VTK, real MCP/IK; user Codex registration skipped for isolated test |
| Repair | Removed ezc3d in isolated environment: doctor failed as expected; doctor -Repair restored locks and passed native MCP/IK and dependency/version/source checks |
| Upgrade/rollback | Actual v0.8→v1.0 activation with throwaway Codex config, launched 80-tool native server, preserved roots/results/temp/scripts exactly; new examples not implicitly authorized; rollback preserved latest unrelated settings |
| Workflow checks | Both workflows passed actionlint 1.7.12 with declared custom runner labels; all PowerShell scripts parsed |

Machine evidence: [windows11-v1.0.json](validation/windows11-v1.0.json). Earlier
subsystem reports can show 79 tools before final GUI reconfiguration was added;
final stdio/GUI reports show 80. Historical evidence remains under validation
and docs/VERIFIED-v0.x.md.

Original synthetic models/C3D/meshes and the offline viewer demo are bundled.
Human input files are not redistributed; only hashes, metrics and declared scope
are included. Human Moco uses short windows and an explicitly changed model.
Objective-only agreement is labeled `objective_only`, not complete state/control
convergence, full gait-cycle validation or physiological validity. RRA residual
reduction is measured rather than promised.

The final source ZIP is re-extracted onto the isolated installation and checked
against its final manifest, with adapter tests, native self-check and doctor.
The accompanying external release-validation JSON records that archive SHA256
and actual results. Fresh-directory installation is **not a clean Win11 VM**.

Both workflows are prepared and locally linted. **Hosted Actions, remote Release
creation and the self-hosted workflow have not run on GitHub**, because no target
repository was supplied. Desktop CI requires a dedicated Win11 runner with the
GUI/startup plugin/resources. No repository or tag was invented or published.
