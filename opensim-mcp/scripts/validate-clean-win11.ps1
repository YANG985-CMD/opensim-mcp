param([Parameter(Mandatory=$true)][string]$TempRoot)
$ErrorActionPreference='Stop'
$projectDir=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if ((Test-Path -LiteralPath (Join-Path $projectDir '.venv')) -or (Test-Path -LiteralPath (Join-Path $projectDir '.api46-venv'))) {
    throw 'Run inside a clean Windows 11 VM using a fresh source extraction, not an existing installed project.'
}
$osInfo=Get-CimInstance Win32_OperatingSystem
if ($osInfo.ProductType -ne 1 -or [int]$osInfo.BuildNumber -lt 22000) {throw 'This gate requires actual Windows 11 desktop.'}
$scratch=[IO.Path]::GetFullPath($TempRoot)
if ($scratch -eq [IO.Path]::GetPathRoot($scratch)) {throw 'Choose a dedicated test folder.'}
New-Item -ItemType Directory -Path $scratch -Force | Out-Null
$baseline=[ordered]@{os_caption=$osInfo.Caption;os_version=$osInfo.Version;os_build=$osInfo.BuildNumber;fresh_source_extraction=$true;existing_python_on_path=[bool](Get-Command python -ErrorAction SilentlyContinue);existing_uv_on_path=[bool](Get-Command uv -ErrorAction SilentlyContinue);clean_vm_status='Requires operator confirmation of a fresh VM snapshot; script does not attest host cleanliness.'}
[IO.File]::WriteAllText((Join-Path $scratch 'clean-win11-baseline.json'),($baseline|ConvertTo-Json),(New-Object Text.UTF8Encoding($false)))
& (Join-Path $PSScriptRoot 'install.ps1') -TempRoot $scratch -WithTests -SkipCodexRegistration
if ($LASTEXITCODE -ne 0) {throw 'Clean Windows install failed; preserve baseline and logs.'}
. (Join-Path $PSScriptRoot 'env.ps1') -TempRoot (Join-Path $scratch 'tests') -ResultsRoot (Join-Path $scratch 'results') -EnableScripts
$server=Join-Path $projectDir '.venv\Scripts\python.exe'
& $server -B -m pytest (Join-Path $projectDir 'tests') --basetemp (Join-Path $scratch 'pytest') --junitxml (Join-Path $scratch 'pytest.xml') -q
if ($LASTEXITCODE -ne 0) {throw 'Clean Windows adapter regression failed.'}
foreach($name in @('smoke_v10','smoke_v11','smoke_wearable','smoke_tracking')) {
    & $server -B (Join-Path $PSScriptRoot ($name+'.py')) --report (Join-Path $scratch ($name+'.json'))
    if ($LASTEXITCODE -ne 0) {throw "Clean Windows native regression failed: $name"}
}
& $server -B -m opensim_mcp.doctor --report (Join-Path $scratch 'doctor.json')
if ($LASTEXITCODE -ne 0) {throw 'Clean Windows doctor failed.'}
Write-Host "Clean-VM test commands completed on the operator-provided machine. Evidence: $scratch"
