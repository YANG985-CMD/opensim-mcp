# Contributing

Supported user OS: Windows 11 x64. Use Python 3.12 and the hashed test lockfile.
Follow the README setup and run pytest with a dedicated `--basetemp` folder,
then run `scripts/smoke_mcp.py`. Use `--run-ik` only where a compatible OpenSim
installation exists. Do not label a mocked or skipped native test as a successful
OpenSim simulation.

For the core native/API workflows, provision the API environment and run
`scripts/smoke_extended.py --examples examples`. Add `--gui` only after explicitly
attaching the GUI bridge (automatically with the installed startup plugin); this changes synthetic GUI/API models and tests timeout
recovery. The script verifies analytic 20 N/15 N forces and model/pose round trips.

For v0.4 run scripts/smoke_v04.py with a dedicated test temp/results pair.
Opt-in regression_human.py and regression_gui_lifecycle.py require local official
resources; see VERIFIED.md. Check native process-tree termination rather than
marking a UI cancellation request as successful termination. Update the executed
validation record only after actually running the relevant check.

Add tests for new trust boundaries and numerical behavior. Keep native code in
separate processes, stdout protocol-only, and inputs immutable. Add new workflows
as structured tools, with explicit input dependencies, units, output validation
and provenance. Document compatibility changes before updating dependency pins.

Never commit virtual environments, caches, local Codex configuration, native
OpenSim binaries, third-party models without their licenses, or participant data.
The CI uses a hosted Windows Server runner for adapter and native wheel checks;
actual Windows 11/GUI validation is a separate requirement. The installer must
accept Server only through the explicit CI flag.

For the current release, use install.ps1 -WithTests -SkipCodexRegistration with
an external TempRoot. After pytest, run smoke_profiles.py, smoke_tracking.py,
smoke_projects.py, regression_projects.py and smoke_v08.py with --report paths
in that scratch directory, then smoke_v04.py with --examples and --report.
These require the real native API; a mocked test is not an alternative.
Use separate scratch/result roots for concurrent suites. Native process
cancellation tests may end their own synthetic test jobs.

Run actionlint against .github/workflows/windows.yml and parse PowerShell scripts
before committing workflow/install changes. Keep actions pinned to reviewed
commits. Dependency upgrades require refreshed hashes and native regressions.
Build releases with scripts/package_source.py --output <formal-delivery-folder>;
it generates a source hash manifest and checks ZIP contents. Inspect the inventory
for private files before publishing. A version tag must match __version__ and
pyproject.toml. Hosted CI must pass before the release job publishes ZIP/SHA256.

For v1.1 also run smoke_v11.py, smoke_wearable.py and
smoke_lower_limb_wearable.py. Human-cycle regression is opt-in and uses separately
installed Gait2354 inputs. Preserve needs_review when complete mesh/trajectory
criteria fail; native solver success is not acceptance. GUI lifecycle tests must
own their windows and include independent-process conflict/undo checks.
Installation fault injection may target only a new owned extraction with fake
CODEX_HOME. See docs/WIN11_REPRO.zh-CN.md; do not equate fresh-directory tests with
a clean Windows VM. CAD native-file export is a separate optional integration;
never close another task's CAD documents to free test capacity.
