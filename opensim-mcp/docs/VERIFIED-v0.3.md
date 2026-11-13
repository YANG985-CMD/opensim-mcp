# Actual local verification — 2026-10-28, v0.3.0

Host: Windows 11 x64 (10.0.26200), MCP server CPython 3.12.13, MCP SDK 1.29.1.
This document distinguishes executed tests from compatibility expectations.

| Runtime | Observed version |
| --- | --- |
| Main server | opensim-mcp 0.3.0, CPython 3.12.13 |
| Official PyPI API wheel | opensim 4.6, wheel build 2, native 4.6-2026-06-22-85aaf64 |
| API numerical library | NumPy 2.5.4, CPython 3.12.13 x64 |
| GitHub GUI package | 4.6_beta / OpenSim-4.6-2026-04-11-a0637fa-win64.exe |
| That GUI's native core and CLI | 4.5.2-2026-02-17-1df1a24, built 2026-02-20 |
| Legacy retained installation | 4.3-2021-08-27-4bc7ad9; Python 3.8.20 / NumPy 1.20.3 |

The downloaded GUI EXE's SHA-256 matched the official GitHub asset digest:
180e2a5ce4cb7449792d0ec6aaa1b9e93da8c329a665f63606e2485c392524d9.
The side-by-side GUI installer exited 0. Its 4.6 package label does not establish
a final 4.6 native core; the runtime probe above is authoritative for these tests.

| Executed check | Result |
| --- | --- |
| Dependency/project setup | Main hashed setup and editable installation passed; package renamed from opensim-mcp-local to opensim-mcp |
| API 4.6 helper | Hashed wheel installation/import probe passed; no GUI SDK mixed into the wheel process |
| Adapter tests | 54 passed, including XML/path/data/parameter limits, disabled scripts, child-process timeout/exit, GUI heartbeat identity/expiry, Unicode bootstrap paths and invalid backend configuration |
| Real stdio MCP | 22 tools listed; structured calls worked |
| Persistent API | Model load/finalize/init; mass changed to 2.5 kg; invalid mass rejected; subsequent value unchanged |
| Scripts | Persistent variable 41→42; captured output/exception; script file executed; timed-out worker terminated and new session started empty |
| IK through API 4.6 | 11 requested samples; maximum analytic slider error 1.3877787807814457e-17 m, below 1e-6 m tolerance |
| ID through API 4.6 | 11 samples, force 20 N; +5 N assistance produced 15 N |
| Static Optimization through API 4.6 | 20 N unassisted / 15 N assisted; finite bounded activation |
| MuscleAnalysis through API 4.6 | Muscle path 1 m and translational moment arm 1 |
| GUI 4.6_beta startup | Native plugin dispatched bootstrap automatically; actual requests and fresh heartbeat succeeded |
| API 4.6 ↔ GUI core 4.5.2 | Load model/motion, set pose, pull, edit mass to 3 kg, push and pull again; 0.03 m pose and 3 kg mass preserved; stale signature rejected |
| GUI restart | Old process 43380 replaced by 54432; the new process answered status without a manual bootstrap |
| GUI launcher helper | start-gui.ps1 launched a new process with E: preferences/cache/Java temporary paths; startup plugin attached without a manual bootstrap |
| Inputs | Original synthetic model hash unchanged after integration |
| Legacy 4.3 with current v0.3 adapter | Real 22-tool stdio/API/script/IK/ID/MA/SO regression passed using CLI 4.3 and Python 3.8.20; GUI not included in that run |
| Codex config | opensim_mcp block updated to E: / API 4.6; TOML comparison verified all unrelated settings unchanged; CLI readback passed |

The comprehensive executed workflow is scripts/smoke_extended.py --examples
examples --gui, using wheel/API mode. A sanitized JSON record is in validation/.
The restart check queries a fresh process and does not infer connection merely
from an old heartbeat. The temporary GUI cache was refreshed after replacing the
initial development JAR; stale NetBeans bytecode had otherwise survived updates.

The separate API 4.6 analytic IK check measured the error reported above.
Previous v0.2 verification on OpenSim 4.3 also established its GUI pose/model
workflow. Current startup automation was tested on the beta distribution listed
above; installing the startup plugin into 4.3 does not itself prove its startup
behavior there.

Not validated: real participant studies, physiological conclusions, arbitrary
native plugins/contact-mesh dependencies, every 4.6 model in the older GUI core,
Moco optimization, scaling, joint reactions, hosted CI, or remote GitHub publishing.
Only Windows 11/Python 3.12 x64 has the full current test record.

The SDK remains pinned to the v1 MCP API; upgrading to SDK v2 requires migration.
Codex's existing desktop connection must reload before it adopts changed env/tool
descriptions. The real stdio tests use the new configuration independently.
