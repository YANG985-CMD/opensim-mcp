param([Parameter(Mandatory=$true)][string]$Record)
$ErrorActionPreference='Stop'
$projectDir=Split-Path -Parent $PSScriptRoot
& (Join-Path $projectDir '.venv\Scripts\python.exe') -B (Join-Path $PSScriptRoot 'manage_release.py') rollback --record $Record
if ($LASTEXITCODE -ne 0) { throw 'Rollback refused; existing settings have not been overwritten.' }
