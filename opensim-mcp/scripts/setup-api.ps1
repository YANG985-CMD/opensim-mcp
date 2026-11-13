param(
    [Parameter(Mandatory=$true)][string]$OpenSimRoot,
    [Parameter(Mandatory=$true)][string]$TempRoot,
    [string]$Python = '3.8'
)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$sdkDir = Join-Path $OpenSimRoot 'sdk\Python'
if (-not (Test-Path -LiteralPath (Join-Path $sdkDir 'opensim\version.py'))) { throw 'OpenSim SDK Python bindings not found.' }
if ((Get-Content -LiteralPath (Join-Path $sdkDir 'opensim\version.py') -Raw) -notmatch '4\.3') {
    throw 'This helper targets the legacy OpenSim 4.3 SDK. For newer builds configure a separately matched API environment as described in README.md.'
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv before using this helper.' }
$scratchParent = [IO.Path]::GetFullPath($TempRoot)
if ($scratchParent -eq [IO.Path]::GetPathRoot($scratchParent)) { throw 'Use a dedicated TempRoot folder.' }
$setupDir = Join-Path $scratchParent ('api-setup-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $setupDir -Force | Out-Null
$savedEnv = @{}
foreach ($key in @('TEMP','TMP','UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','PYTHONDONTWRITEBYTECODE','OPENSIM_MCP_INSTALL_DIR','OPENSIM_MCP_API_SDK')) {
    $savedEnv[$key] = [Environment]::GetEnvironmentVariable($key,'Process')
}
try {
    $env:TEMP = $setupDir
    $env:TMP = $setupDir
    $env:UV_CACHE_DIR = Join-Path $setupDir 'uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectDir 'runtimes\python'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $apiEnv = Join-Path $projectDir '.api-venv'
    $apiPython = Join-Path $apiEnv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $apiPython)) {
        & uv venv --python $Python $apiEnv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python API environment.' }
    }
    & $apiPython -B -c 'import sys; assert sys.version_info[:2] == (3,8)'
    if ($LASTEXITCODE -ne 0) { throw 'API Python version does not match the SDK.' }
    & uv pip install --python $apiPython --require-hashes -r (Join-Path $projectDir 'requirements-api43.lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'API dependency installation failed.' }
    $env:OPENSIM_MCP_INSTALL_DIR = [IO.Path]::GetFullPath($OpenSimRoot)
    $env:OPENSIM_MCP_API_SDK = [IO.Path]::GetFullPath($sdkDir)
    $probe = Join-Path $setupDir 'probe.py'
    @'
import runpy, sys
worker = runpy.run_path(sys.argv[1], run_name='opensim_api_probe')
osim = worker['bootstrap']()
print(osim.GetVersionAndDate())
'@ | Set-Content -LiteralPath $probe -Encoding utf8
    & $apiPython -B $probe (Join-Path $projectDir 'src\opensim_mcp\worker.py')
    if ($LASTEXITCODE -ne 0) { throw 'OpenSim API import probe failed.' }
    Write-Host "API environment ready: $apiPython"
    Write-Host 'Use env.ps1 / print-codex-config.ps1 with -OpenSimRoot and optionally -EnableScripts.'
}
finally {
    foreach ($key in $savedEnv.Keys) {
        if ([string]::IsNullOrEmpty($savedEnv[$key])) { Remove-Item -LiteralPath "Env:$key" -ErrorAction SilentlyContinue }
        else { [Environment]::SetEnvironmentVariable($key,$savedEnv[$key],'Process') }
    }
    $resolvedSetup = [IO.Path]::GetFullPath($setupDir)
    $allowedTemp = $scratchParent.TrimEnd('\') + [IO.Path]::DirectorySeparatorChar
    if ($resolvedSetup.StartsWith($allowedTemp,[StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $resolvedSetup -Recurse -Force }
}
