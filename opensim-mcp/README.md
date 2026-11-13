# OpenSim MCP v1.4.1 for Windows 11

An independent **94-tool MCP server** for Codex: inspect/edit OpenSim models,
run biomechanics pipelines, attach the GUI automatically, recover native state,
and export offline interactive 3D motion players. Server name: **opensim_mcp**.
OpenSim Core is unchanged. This is not an official OpenSim/OpenAI product.

The 1.4.1 update adds explicit CAD mass/COM/inertia conversion and physical
inertia validation before wearable assembly, plus native save/reopen readback.
See [mass-property conventions and limits](docs/MASS_PROPERTIES.zh-CN.md).
The Windows 11 bytecode installer is published in the public [download repository](https://github.com/YANG985-CMD/opensim-mcp/releases/tag/v1.4.1).

[中文安装与功能说明](README.zh-CN.md) · [All tools](docs/TOOLS.md) ·
[Executed validation](VERIFIED.md) · [v1.1 workflows](docs/V11_WORKFLOWS.zh-CN.md) ·
[3D demo](examples/viewer-demo.html) · [Security](SECURITY.md)

## Generic visualization and application exchange

Bind explicit MATLAB/CSV/MOT/STO signals to native upper- or lower-limb scenes,
click a curve to locate a pose, export source samples and selected context, and
verify portable workspace assets. SolidWorks STL uses the existing explicit-unit
CAD assembly workflow. [Usage and limits](docs/VISUALIZATION_INTEROP.zh-CN.md).
This is offline file exchange; live multi-application synchronization is future work.

## v1.4 workbench

Simple side-by-side native scenes with one timeline, linked camera/selection,
coordinate/signal/force comparisons, marker/frame-origin measurements, and portable
view-state save/restore. [Workbench guide](docs/WORKBENCH.zh-CN.md).

## Install and run

Verify the source ZIP against its trusted SHA256, extract into the final location
(for example `E:\opensim-mcp`), and double-click **install.cmd**. Restart Codex.
Windows 11 x64 and first-install internet access are required; Python need not
be preinstalled. GUI installation is optional and is not bundled or upgraded.

```powershell
Set-Location 'E:\opensim-mcp'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime' -OpenSimRoot 'E:\OpenSim 4.6'
```

Omit `-OpenSimRoot` for API-only use. The installer uses CPython 3.12.13, separate
locked server/API environments, a pinned hash-checked uv bootstrap when needed,
and a real MCP/IK check. It merges only this server into Codex and saves a private
backup. Arbitrary scripts default to disabled. `-SkipCodexRegistration` generates
`config/opensim_mcp.generated.toml` for manual merging. Replace all paths in the
[Codex configuration example](config/codex.example.toml).

Double-click **doctor.cmd** for dependency, native capability, version and source
checks. Close Codex before **doctor.cmd -Repair** if packages are in use. Repair
reinstalls pinned dependencies/API and preserves source edits, models and Codex
configuration. Missing native VC++ x64 runtime libraries are reported. See the
[engineering guide](docs/ENGINEERING.zh-CN.md). Do not move installed virtual
environments; install a new release in its final location instead.

To verify without Codex:

```powershell
. .\scripts\env.ps1 -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-runtime'
.\.venv\Scripts\python.exe -B .\scripts\smoke_mcp.py --examples "$PWD\examples" --run-ik
```

The server command is `.\.venv\Scripts\python.exe -B -m opensim_mcp.server`;
it waits for a stdio client. [Side-by-side upgrade/rollback](docs/UPGRADE.zh-CN.md)
preserves existing input/result/temp roots and scripting preferences.

## Capabilities and limits

| Area | Delivered behavior |
| --- | --- |
| Model/API | Static XML summary, persistent native worker, component/API discovery, code diagnostics, bounded named native-state reads |
| Editing/recovery | Parameter and supported topology previews, revision checks, atomic commit/undo/redo, full-state checkpoints and persistent rollback journals, explicit native model/state/time recovery after worker/server failure |
| GUI | Startup-plugin attachment, selection/capture, model/motion/pose control, explicit API/GUI sync, process/heartbeat checks and in-place v1 bridge configuration reload |
| Analyses | IK, ID, MuscleAnalysis, SO, scaling/MarkerPlacer, reserves/residuals, JointReaction, RRA, Moco/Track/Inverse, successive mesh and finite sensitivity studies |
| Data/jobs | C3D/TRC/force-platform conversion with explicit axes/sign/body mapping, full muscle-project template, async progress/cancel/history, verified pipeline cache/resume, quantified reports and portable project bundles |
| Visualization | Client-visible plots/images, native pose views; offline WebGL OBJ/STL/self-contained VTP/primitive surface animation, orbit/zoom, timeline, joint curves, comparison motion and marker-error colors |
| Engineering | One-click setup, locked dependencies, limited repair, observed compatibility, source ZIP/checksums, GitHub CI/tag-release and optional self-hosted Win11 GUI workflows |

Topology support is bounded to the documented bodies, Pin/Slider/Weld joints,
markers and coordinate actuators, set-member removal/rename and supported joint
reconnection. It is not a universal component editor. Recovery restores native
definition, all named native states and time, not Python variables, GUI workspace
or arbitrary scripts' filesystem/network side effects. No script is replayed.

API and GUI models are distinct. Explicit `sync_gui_model(direction="pull")`
imports a GUI snapshot; `direction="push"` loads a new active GUI version while
retaining prior GUI models. Auto attachment does not merge sessions or close
another user's GUI. See [plugin setup](gui-autobridge/README.md).

All paths must be absolute and within configured input roots or results. Native
models, C3D and meshes must be trusted. Force assumptions and N/m/Nm units are
explicit; coordinate inputs declare inDegrees, API values use rad/m. Arbitrary
Python is opt-in (`OPENSIM_MCP_ENABLE_SCRIPTS='1'`) and runs with the Windows user's
permissions. This is a local single-user service, not an OS sandbox or a clinical
validation system. Solver success or objective-only mesh agreement is not
physiological validity. Read [SECURITY.md](SECURITY.md).

[C3D/RRA/muscle projects/Moco studies](docs/V09_WORKFLOWS.zh-CN.md) ·
[Projects](docs/PROJECTS.zh-CN.md) · [Marker/actuator profiles](docs/PROFILES.zh-CN.md) ·
[Reference Moco](docs/MOCO_REFERENCE.zh-CN.md)

## Compatibility and reproduction

Primary tested profile: **Windows 11 x64 / CPython 3.12.13 / official opensim 4.6
wheel build 2 / NumPy 2.5.4**, observed core `4.6-2026-06-22-85aaf64`.
Server Python is constrained to **3.12**. Hashed locks pin mcp 1.29.1, pydantic
2.14.1, defusedxml 0.7.1, matplotlib 3.11.2, ezc3d 1.7.2 and vtk 9.7.1. MCP SDK v2
requires a port. The retained GUI is the official 4.6_beta distribution with
actual core **4.5.2-2026-02-17-1df1a24**, not a verified final 4.6 GUI. Do not mix
GUI SDK/DLLs with the official wheel environment. Legacy 4.3/Python 3.8 is covered
only by documented core and cross-version regressions.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 `
  -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-checks' -WithTests -SkipCodexRegistration
. .\scripts\env.ps1 -TempRoot 'E:\simulink\_codex_tmp\opensim-mcp-checks' `
  -ResultsRoot 'E:\simulink\_codex_tmp\opensim-mcp-checks\results' -EnableScripts
.\.venv\Scripts\python.exe -B -m pytest --basetemp 'E:\simulink\_codex_tmp\opensim-mcp-checks\pytest'
.\.venv\Scripts\python.exe -B .\scripts\smoke_v10.py --report 'E:\simulink\_codex_tmp\opensim-mcp-checks\v10.json'
```

[VERIFIED.md](VERIFIED.md) records 175 adapter tests and actual native, GUI,
browser, human-example, installation and rollback checks, including their limits.
Original synthetic fixtures are included; third-party human/force-plate data is
read from a separately installed official example and never redistributed.
Human Moco now includes one measured force-event cycle (0.6183–1.8533 s), full
100-state/77-control assessment and native actuator/constraint audits. The measured
mesh differences require review; no physiological or full convergence claim.

GitHub workflows are locally linted and ready for your repository. A matching
`v1.1.0` tag releases the tested ZIP only after CI success. Hosted Windows Server
CI and optional self-hosted Windows 11 GUI tests are separate. Neither hosted CI,
remote Release creation nor a clean Windows 11 VM test has been executed here.

MIT license covers the adapter and original fixtures; dependencies retain their
own licenses. The source ZIP excludes OpenSim binaries, environments, private
configuration, session state/results and participant trials.


## New in v1.1

Seven structured tools add force-event gait cycles, explicit coordinate resampling,
complete named mesh checks, native actuator/constraint audits, CAD wearable
assembly, coupled device motions and matched welded-mass/ideal-assist ID.
GUI operations now share a Windows cross-process lock and atomic observed-state
tokens; cross-session pose undo is rejected. Save work and restart an older GUI
bridge before v1.1 writes.

[Wearable 3D demo](examples/wearable-demo.html) ·
[CAD/biomechanics details](docs/V11_WORKFLOWS.zh-CN.md) ·
[Windows/offline reproduction](docs/WIN11_REPRO.zh-CN.md)

Trusted native SolidWorks documents require optional SolidWorks MCP/CAD software
to export meshes; a CAD converter is not bundled. Device segment/frame/mass/COM/
central inertia/joint axes are explicit. Supported rigid constraints are not an
automatic strap/contact/soft-tissue model. Real human-model cuff assembly and
matched ID were exercised with original illustrative devices; the user's actual
CAD/device has not been supplied. The packaged lower-limb demo is schematic.

The installer supports warm offline repair and actual native Moco/IPOPT checks,
then publishes Codex registration. Fresh Unicode/space paths, missing dependency/
solver faults and offline cache reuse passed locally; clean-OS VM execution and
remote GitHub Actions remain unexecuted.

## Lower-limb device studies

Version 1.2 adds explicit static-optimization muscle-force studies, verified welded-device mass comparisons and source-traceable muscle volume estimates/measurements. The offline viewer supports force/activation color, picking, paired force curves, numeric-quality status and CSV export. See [workflow and limits](docs/EXOSKELETON_STUDIES.zh-CN.md).

[Original analytic muscle-force demo](examples/muscle-force-demo.html) (synthetic, not a human model).
