# Executed Windows 11 validation — v0.4.0, 2026-10-28

80 adapter tests passed. A real local stdio client discovered 47 tools and
exercised the added workflows; this is not a mocked or hosted-CI native result.
The sanitized machine-readable record is [windows11-v0.4.json](validation/windows11-v0.4.json).
The older [v0.3 record](docs/VERIFIED-v0.3.md) is retained separately.

| Runtime | Observed value |
| --- | --- |
| OS/server | Windows 11 x64 10.0.26200; CPython 3.12.13 |
| MCP / plotting | MCP SDK 1.29.1; Matplotlib 3.11.2, isolated Agg renderer |
| OpenSim wheel | 4.6 build 2; native 4.6-2026-06-22-85aaf64; NumPy 2.5.4 |
| GUI package | Official GitHub 4.6_beta, 4.6-2026-04-11-a0637fa |
| GUI's actual core | 4.5.2-2026-02-17-1df1a24; Python GUI bridge 0.4.0 |
| Retained legacy | Native 4.3-2021-08-27-4bc7ad9; CPython 3.8.20 / NumPy 1.20.3 |

The GUI test package is not described as a final native 4.6 GUI. The user deferred
the final SimTK GUI installer because its download requires an account.
The startup module's unchanged Java bytecode has specification version 0.3;
it automatically loads the separate, updated Python bridge 0.4 on launch.

| Executed check | Result |
| --- | --- |
| Adapter suite | 80 passed; XML/path/units, invalid workflows, time alignment/interpolation, checkpoint tamper, heartbeat, real process-tree cancellation/owner crash, progress-file reader locks |
| Discovery/diagnostics | Installed API docs, native component paths/properties/sockets, syntax/API typo diagnostics and actual script traceback line/source |
| Model history | Structured edit, guarded undo/redo, persistent checkpoint/restore and recovery savepoint |
| Client media | PNG contents returned through MCP and decoded with Pillow; PNG/SVG artifacts created; actual curve, pose and GUI PNG visually inspected |
| Scaling | Manual native scale initialized/reopened, target mass 2 kg and zero mass error; measured M1–M2 distance scales body Y by 2, zero pair error |
| JointReaction | Analytic support force 20 N, moment 0 N·m; SO force output successfully feeds a separate muscle-model JR run |
| Moco/CasADi | Solve_Succeeded; objective 48.00000000000038 vs analytic 48; zero sampled bound/endpoint violation |
| Moco refinement | 10→20 intervals; relative objective change 3.49646237888491e-13 |
| Independent IK assessment | Analytic marker RMS below 1e-6 m threshold; native marker locations used |
| Async completion | Native IK executed in an isolated job and published verified results |
| Async cancellation | In-flight native Moco process terminated; descendant process verified stopped; cancelled result not published |
| History | Completed job read by a second MCP process after connection restart; failed/cancelled/interrupted cases covered |
| GUI | Actual Navigator body selection/readback, pose edit/undo and scoped Swing PNG returned through MCP |
| GUI lifecycle | Two different fresh GUI processes auto-attached without manual bootstrap; old heartbeat expired |
| Daily startup fix | Official resource folder registered; first-launch marker/prefs retained in project state/gui-user; var/log junction points to temp; normal GUI restarted with bridge 0.4 and no resource dialog |
| Legacy v0.4 regression | Existing native API/scripts/timeout/IK/ID/SO/MA checks passed with CLI/API 4.3; input fixture unchanged |

## Official human model and measured force plates

The installed Gait2354_Simbody subject01 example was read without changing its
inputs. Files are fingerprinted in the JSON record and are not redistributed.
The loaded model has 12 bodies, 12 joints, 23 coordinates, 39 markers and 54
muscles, total mass 72.6 kg.

- Inverse dynamics with the supplied measured forces/points/torques and 6 Hz
  coordinate filtering: 73 frames over 0.4–1.6 s.
- Pelvis residual force RMS: 52.93971814858892 N (7.43574227363609% body weight);
  peak: 186.99146817494963 N. These are reported metrics, not an acceptance claim.
- Reference motion marker RMS: 0.02199652277590968 m; maximum: 0.08497943944525618 m.
  Its time grid differs from the TRC, so explicit linear marker interpolation was used.
- A fresh 11-frame IK solve on the measured TRC: RMS 0.019001125863383348 m,
  maximum 0.06491326655870495 m. It remains a software regression with reported fit.
- Saved 4.6 XML loaded in API 4.3, saved again and reloaded in 4.6. Counts and mass
  matched. ID force/moment tables from the two runtimes matched numerically
  (maximum absolute column difference 0, per-column tolerance 0.1 N or N·m).

This does not establish preservation of every property in every newer component,
or validate muscle forces/contact physiology in that human study.

## Reproduce

Start from the README setup; use a dedicated test temp/results pair and trusted
installed example files. Replace the resource and legacy-runtime paths below.

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Set-Location 'E:\simulink\mcp_servers\opensim-mcp'
$check = 'E:\simulink\_codex_tmp\opensim-v04-check'
. .\scripts\env.ps1 -TempRoot (Join-Path $check 'runtime') -ResultsRoot (Join-Path $check 'results') -OpenSimRoot 'E:\OpenSim 4.6' -EnableScripts
.\.venv\Scripts\python.exe -B -m pytest --basetemp (Join-Path $check 'pytest')
.\.venv\Scripts\python.exe -B .\scripts\smoke_v04.py --examples .\examples --report (Join-Path $check 'stdio.json')
.\.venv\Scripts\python.exe -B .\scripts\regression_human.py --resources 'E:\OpenSimExamples\Gait2354_Simbody' --legacy-python 'E:\simulink\mcp_servers\opensim-mcp\.api-venv\Scripts\python.exe' --legacy-root 'D:\OpenSim 4.3' --report (Join-Path $check 'human.json')
.\.venv\Scripts\python.exe -B .\scripts\regression_gui_lifecycle.py --opensim-root 'E:\OpenSim 4.6' --resources-root 'E:\OpenSimResources\4.6' --examples .\examples --report (Join-Path $check 'gui.json')
~~~

The GUI regression owns its isolated profile and two GUI processes. Its native
selection/image/undo checks use synthetic fixtures. Do not use a test bridge
folder already owned by a user GUI. The broader core workflow remains
scripts/smoke_extended.py; --gui also exercises API↔GUI pose/model sync.

Not validated: hosted CI, all OpenSim/GUI releases, arbitrary external plugins,
clinical conclusions, general MarkerPlacer or all Moco problem families. Matplotlib
and native calculations run in isolated process trees; these limits do not make
arbitrary trusted Python an OS security sandbox.
