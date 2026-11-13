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
if (-not $Cli -and $ToolBackend -eq 'cli') { throw 'CLI backend requires -Cli or -OpenSimRoot.' }
if ($InputRoots.Count -eq 0) { $InputRoots = @((Join-Path $projectDir 'examples')) }
if (-not $ResultsRoot) { $ResultsRoot = Join-Path $projectDir 'results' }
$pythonPath = (Join-Path $projectDir '.venv\Scripts\python.exe').Replace('\','/')
$cliPath = $Cli.Replace('\','/')
$resultsPath = ([IO.Path]::GetFullPath($ResultsRoot)).Replace('\','/')
$tempPath = ([IO.Path]::GetFullPath($TempRoot)).Replace('\','/')
$rootsJson = ConvertTo-Json -Compress -InputObject @($InputRoots | ForEach-Object { ([IO.Path]::GetFullPath($_)).Replace('\','/') })
$apiEnvName = if ($ApiMode -eq 'wheel') { '.api46-venv' } else { '.api-venv' }
if (-not $ApiPython -and (Test-Path -LiteralPath (Join-Path $projectDir "$apiEnvName\Scripts\python.exe"))) { $ApiPython = Join-Path $projectDir "$apiEnvName\Scripts\python.exe" }
$apiLines = @()
if ($ApiPython) { $apiLines += "OPENSIM_MCP_API_PYTHON = '$($ApiPython.Replace('\','/'))'" }
if ($OpenSimRoot) {
    $apiLines += "OPENSIM_MCP_INSTALL_DIR = '$($OpenSimRoot.Replace('\','/'))'"
}
$sdkPath = if ($OpenSimRoot -and $ApiMode -eq 'sdk') { (Join-Path $OpenSimRoot 'sdk/Python').Replace('\','/') } else { '' }
$apiLines += "OPENSIM_MCP_API_SDK = '$sdkPath'"
$apiLines += "OPENSIM_MCP_TOOL_BACKEND = '$ToolBackend'"
$enabled = if ($EnableScripts) { '1' } else { '0' }
$apiLines += "OPENSIM_MCP_ENABLE_SCRIPTS = '$enabled'"
$apiBlock = $apiLines -join "`n"
if (($pythonPath + $cliPath + $resultsPath + $rootsJson + $tempPath + $ApiPython + $OpenSimRoot).Contains("'")) {
    throw 'A path contains an apostrophe; escape it manually using TOML basic strings.'
}
@"
[mcp_servers.opensim_mcp]
command = '$pythonPath'
args = ['-B', '-m', 'opensim_mcp.server']
startup_timeout_sec = 20
tool_timeout_sec = 180

[mcp_servers.opensim_mcp.env]
OPENSIM_MCP_CLI = '$cliPath'
OPENSIM_MCP_ALLOWED_ROOTS = '$rootsJson'
OPENSIM_MCP_RESULTS_ROOT = '$resultsPath'
OPENSIM_MCP_TEMP_ROOT = '$tempPath'
OPENSIM_MCP_TIMEOUT_SEC = '120'
PYTHONDONTWRITEBYTECODE = '1'
TEMP = '$tempPath'
TMP = '$tempPath'
$apiBlock
"@
