param([string]$Python='python')
$ErrorActionPreference='Stop'
$taskScratch='E:\simulink\_codex_tmp\solidworks_local_setup'
New-Item -ItemType Directory -Path $taskScratch -Force | Out-Null
$env:TEMP=$taskScratch
$env:TMP=$taskScratch
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PIP_CACHE_DIR=Join-Path $taskScratch 'pip-cache'
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'))) {
    & $Python -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or newer is required.' }
}
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -B -m pip install -r (Join-Path $PSScriptRoot 'requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Output 'Dependencies installed. Use integration/configure_codex.py to prepare or apply the server entry.'
