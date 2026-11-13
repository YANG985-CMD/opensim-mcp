param([string]$TempRoot='', [string]$OpenSimRoot='', [switch]$Repair, [switch]$Offline, [switch]$AllowWindowsServer)
$ErrorActionPreference='Stop'
$projectDir=Split-Path -Parent $PSScriptRoot
if (-not $TempRoot) {
    if (Test-Path -LiteralPath 'E:\') { $TempRoot='E:\simulink\_codex_tmp\opensim-mcp-runtime' }
    else { $TempRoot=Join-Path ([IO.Path]::GetTempPath()) 'opensim-mcp' }
}
if ($Repair) {
    & (Join-Path $PSScriptRoot 'install.ps1') -TempRoot $TempRoot -OpenSimRoot $OpenSimRoot -Repair -Offline:$Offline -SkipCodexRegistration -AllowWindowsServer:$AllowWindowsServer
    if ($LASTEXITCODE -ne 0) { throw 'Repair failed.' }
}
$server=Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $server)) { throw 'Server Python missing. Run install.cmd, or doctor.cmd -Repair.' }
. (Join-Path $PSScriptRoot 'env.ps1') -TempRoot $TempRoot -OpenSimRoot $OpenSimRoot
$report=Join-Path $env:OPENSIM_MCP_TEMP_ROOT ('doctor-'+[guid]::NewGuid().ToString('N')+'.json')
& $server -B -m opensim_mcp.doctor --report $report
if ($LASTEXITCODE -ne 0) { throw "Environment checks failed. Report: $report . Repair: doctor.cmd -Repair" }
Write-Host "Report: $report"
