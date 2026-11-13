param(
    [Parameter(Mandatory=$true)][string]$TempRoot,
    [string]$Python = '3.12'
)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv before using this helper.' }
$scratch = [IO.Path]::GetFullPath($TempRoot).TrimEnd('\')
if ($scratch -eq [IO.Path]::GetPathRoot($scratch)) { throw 'Use a dedicated TempRoot folder.' }
$stage = Join-Path $scratch ('api46-setup-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$savedEnv = @{}
foreach ($key in @('TEMP','TMP','UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','UV_PYTHON_DOWNLOADS','PYTHONDONTWRITEBYTECODE')) {
    $savedEnv[$key] = [Environment]::GetEnvironmentVariable($key,'Process')
}
try {
    $env:TEMP=$stage
    $env:TMP=$stage
    $env:UV_CACHE_DIR=Join-Path $stage 'uv-cache'
    $env:UV_PYTHON_INSTALL_DIR=Join-Path $projectDir 'runtimes\python'
    $env:UV_PYTHON_DOWNLOADS='auto'
    $env:PYTHONDONTWRITEBYTECODE='1'
    $apiEnv=Join-Path $projectDir '.api46-venv'
    $apiPython=Join-Path $apiEnv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $apiPython)) {
        & uv venv --python $Python $apiEnv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python API environment.' }
    }
    & $apiPython -B -c 'import sys; assert sys.version_info[:2]==(3,12) and sys.maxsize>2**32'
    if ($LASTEXITCODE -ne 0) { throw 'This lock requires CPython 3.12 x64.' }
    & uv pip install --python $apiPython --require-hashes -r (Join-Path $projectDir 'requirements-api46.lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'OpenSim 4.6 dependency installation failed.' }
    & $apiPython -B -c 'import opensim; print(opensim.GetVersionAndDate())'
    if ($LASTEXITCODE -ne 0) { throw 'OpenSim 4.6 API import failed.' }
    Write-Host "API ready: $apiPython"
    Write-Host 'Select ApiMode=wheel and ToolBackend=api. Leave OPENSIM_MCP_API_SDK empty.'
}
finally {
    foreach ($key in $savedEnv.Keys) {
        if ([string]::IsNullOrEmpty($savedEnv[$key])) { Remove-Item -LiteralPath "Env:$key" -ErrorAction SilentlyContinue }
        else { [Environment]::SetEnvironmentVariable($key,$savedEnv[$key],'Process') }
    }
    $resolvedStage=[IO.Path]::GetFullPath($stage)
    if ($resolvedStage.StartsWith($scratch+'\',[StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}
