# Dot-source this script: . .\scripts\env.ps1
param(
    [string]$Cli = '',
    [Parameter(Mandatory=$true)][string]$TempRoot,
    [string[]]$InputRoots = @(),
    [string]$ResultsRoot = '',
    [string]$ApiPython = '',
    [string]$OpenSimRoot = '',
    [ValidateSet('wheel','sdk')][string]$ApiMode = 'wheel',
    [ValidateSet('api','cli')][string]$ToolBackend = 'api',
    [switch]$EnableScripts
)
$projectDir = Split-Path -Parent $PSScriptRoot
if (-not $Cli -and $OpenSimRoot) { $Cli = Join-Path $OpenSimRoot 'bin\opensim-cmd.exe' }
if (-not $Cli) {
    $cliCommand = Get-Command opensim-cmd.exe -ErrorAction SilentlyContinue
    if ($cliCommand) { $Cli = $cliCommand.Source }
}
if ($InputRoots.Count -eq 0) { $InputRoots = @((Join-Path $projectDir 'examples')) }
if (-not $ResultsRoot) { $ResultsRoot = Join-Path $projectDir 'results' }
$env:OPENSIM_MCP_ALLOWED_ROOTS = ConvertTo-Json -Compress -InputObject @($InputRoots | ForEach-Object { [IO.Path]::GetFullPath($_).Replace('\','/') })
$env:OPENSIM_MCP_RESULTS_ROOT = [IO.Path]::GetFullPath($ResultsRoot)
$env:OPENSIM_MCP_TEMP_ROOT = [IO.Path]::GetFullPath($TempRoot)
if ($Cli) { $env:OPENSIM_MCP_CLI = $Cli } else { Remove-Item Env:OPENSIM_MCP_CLI -ErrorAction SilentlyContinue }
$apiEnvName = if ($ApiMode -eq 'wheel') { '.api46-venv' } else { '.api-venv' }
if (-not $ApiPython -and (Test-Path -LiteralPath (Join-Path $projectDir "$apiEnvName\Scripts\python.exe"))) { $ApiPython = Join-Path $projectDir "$apiEnvName\Scripts\python.exe" }
if ($ApiPython) { $env:OPENSIM_MCP_API_PYTHON = $ApiPython } else { Remove-Item Env:OPENSIM_MCP_API_PYTHON -ErrorAction SilentlyContinue }
$env:OPENSIM_MCP_TOOL_BACKEND = $ToolBackend
Remove-Item Env:OPENSIM_MCP_API_SDK -ErrorAction SilentlyContinue
if ($OpenSimRoot) {
    $env:OPENSIM_MCP_INSTALL_DIR = [IO.Path]::GetFullPath($OpenSimRoot)
    if ($ApiMode -eq 'sdk') { $env:OPENSIM_MCP_API_SDK = Join-Path $env:OPENSIM_MCP_INSTALL_DIR 'sdk\Python' }
}
$env:OPENSIM_MCP_ENABLE_SCRIPTS = if ($EnableScripts) { '1' } else { '0' }
$env:OPENSIM_MCP_TIMEOUT_SEC = '120'
$env:PYTHONDONTWRITEBYTECODE = '1'
New-Item -ItemType Directory -Path $env:OPENSIM_MCP_TEMP_ROOT -Force | Out-Null
$env:TEMP = $env:OPENSIM_MCP_TEMP_ROOT
$env:TMP = $env:TEMP
