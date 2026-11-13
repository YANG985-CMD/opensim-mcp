# Executed Windows validation — v0.8.0

Actual local execution on **2026-10-29 (Asia/Shanghai)**: Windows 11 x64 build
26200, CPython 3.12.13, official OpenSim 4.6 wheel build 2 / NumPy 2.5.4.
Native runtime: `4.6-2026-06-22-85aaf64`. **132 adapter tests passed**, zero
failures/skips. Fresh stdio discovery returns **65 tools**, adapter **0.8.0**;
the existing Codex configuration was read and verified without changing it.

Structured evidence: [validation/windows11-v0.8.json](validation/windows11-v0.8.json).
Earlier release evidence remains in docs/VERIFIED-v0.3.md through VERIFIED-v0.7.md
and validation/windows11-v0.3.json through windows11-v0.7.json.

## Installation and engineering

- Extracted a source ZIP into a new scratch directory with no project virtual
  environments. Installed standalone CPython, main test dependencies and the
  separate API environment. Actual MCP and 11-frame native IK passed.
- Removed defusedxml in that disposable environment and hid existing uv from
  PATH. `doctor.ps1 -Repair` downloaded the official pinned uv 0.11.26 archive,
  checked its SHA256, reinstalled dependencies/API and reran MCP/IK. Native
  analytic displacement error: **1.3878e-17 m**. Dependency and compatibility
  checks passed. Source differences in this modified development test copy were
  reported as a warning rather than overwritten.
- Registration tests preserve other TOML settings/servers and quoted headers;
  an unsupported layout is rejected before writing. The real existing Codex
  block resolves the installed 0.8.0 source and all 65 tools.
- **actionlint 1.7.12 passed** for the GitHub workflow; all PowerShell scripts
  parsed successfully. Hosted CI/release jobs were **not run** from this local
  workspace. The workflow installs, runs adapter/native regressions, builds
  ZIP/SHA256/evidence and gates release on successful checks plus a matching tag.
  Its hosted Windows Server runner is distinct from this real Win11 machine.

Windows PowerShell **5.1**, used by install.cmd/doctor.cmd, was also executed:
pinned uv bootstrap with the existing uv hidden, complete installation, native
MCP/IK and doctor succeeded. The original nested-quote interpreter check and
redirected-stderr handling were corrected after actual 5.1 runs exposed those
differences. Both output streams now drain directly and the native exit code
determines smoke success. The workflow installer step uses powershell.exe too.
Packaging additionally rejects inconsistent source/pyproject version numbers.

## v0.8 native integration

- Atomic edit preview leaves the current model unchanged. A failing batch
  leaves no partial model edit. A successful batch is one undo/redo step;
  checkpoint rollback restores mass/pose and the journal survives an MCP restart.
- Export/verify/import of a self-contained project bundle succeeded; import
  executed no native model. Its imported seven-stage pipeline then ran
  successfully. Hash tampering and unsafe ZIP names/case collisions are rejected
  by adapter tests.
- Native 3D pose JSON, three equal-scale orthogonal SVGs and HTML were generated.
  The standalone report and scene HTML were rendered with Edge and visually
  inspected. Scene export contains frame/marker coordinates, not surface meshes
  or interactive rotation/animation.

## Analyses, resume and cancellation

- MarkerPlacer moved only selected M2 by **0.1 m**; protected M1/M3 remained
  unchanged. A 0.01 m movement limit, wrong actuator unit and duplicate actuator
  were correctly rejected. Explicit reserve SO/ID force RMS ratio: **9.9981e-5**.
- Native MocoTrack static slider RMS: **7.7365e-9 m**. MocoInverse actuator
  objective: **0**; muscle objective **0.04**, with explicit 5 N external load
  **0.0225**. A 90-degree pin reference correctly became rad with tracking RMS
  **4.4964e-8 rad** and zero sampled bound violation. These are synthetic solves,
  not a human Moco study or a mesh-convergence validation.
- Seven-stage projects computed all stages on first run and reused all seven on
  repeat. Changing only a quality threshold reused the solver cache. Failed-stage
  correction resumed a completed prefix. Tampered cache recomputed the affected
  stage. Canceling a real native Moco process retained only completed stages and
  a subsequent run resumed them. The prior native/GUI suite also confirmed
  asynchronous cancellation and history after an MCP restart.

## Human data, cross-version and GUI

Local official Gait2354 subject01 example: **12 bodies, 12 joints, 23 coordinates,
39 markers, 54 muscles, 72.6 kg**. An actual measured TRC generated an 11-frame
fresh IK result. ID used the measured force plates over **0.4–1.6 s / 73 frames**.
Reference marker RMS: **0.0219965 m**; pelvis residual RMS **52.9397 N**, or
**0.0743574 body weight**. The example project's explicit illustrative 0.05-BW
limit correctly produced **needs_review**. Those limits are not clinical norms.

The model saved/reopened **4.6 → 4.3 → 4.6**, preserving counts/mass. ID results
for this particular trial matched within the 0.1 N/Nm comparison tolerance
(observed maximum difference **0**). Inputs were unchanged. No human trial data
is included in the source ZIP; this is not a general cross-version guarantee.

Two separate GUI launches automatically attached the bridge without manual
bootstrap; the second had a new process, and stale heartbeat expiry was verified.
Selection readback, pose undo and client-visible GUI capture passed. Tests used
their own profiles; the user's GUI model was not changed. Actual GUI native
core **4.5.2-2026-02-17-1df1a24**, bridge **0.4.0**, official **4.6_beta** package.
This is not a verified formal final 4.6 GUI; GUI capture may omit accelerated
embedded browser/3D surfaces.

## Reproduce

Start with README installation using `-WithTests -SkipCodexRegistration` and
separate scratch/results. Set `-EnableScripts` only for the trusted integration
fixtures. Run pytest with `--basetemp` in scratch, then:

```powershell
$py = '.\.venv\Scripts\python.exe'
foreach ($name in @('smoke_profiles','smoke_tracking','smoke_projects','regression_projects','smoke_v08')) {
  & $py -B ".\scripts\$name.py" --report (Join-Path $env:OPENSIM_MCP_TEMP_ROOT "$name.json")
  if ($LASTEXITCODE -ne 0) { throw "Failed: $name" }
}
& $py -B .\scripts\smoke_v04.py --examples "$PWD\examples" `
  --report (Join-Path $env:OPENSIM_MCP_TEMP_ROOT 'prior-native.json')
```

Opt-in `regression_human.py` takes `--resources` pointing at the installed
Gait2354_Simbody folder, and optional absolute `--legacy-python` / `--legacy-root`.
`regression_projects.py --resources ...` additionally checks human project
quality. `regression_gui_lifecycle.py` requires `--opensim-root`, verified
`--resources-root`, absolute `--examples`, `--report` and a dedicated test
scratch/result pair. It owns and terminates its two test GUI process trees.
Do not use a live user's bridge directory for that test.
