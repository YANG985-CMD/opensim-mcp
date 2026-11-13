param(
    [string]$Python = '3.12',
    [Parameter(Mandatory=$true)][string]$TempRoot,
    [switch]$WithTests
)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'Install uv first, or use the Python/pip instructions in README.md.'
}
$scratchParent = [IO.Path]::GetFullPath($TempRoot)
if ($scratchParent -eq [IO.Path]::GetPathRoot($scratchParent)) { throw 'TempRoot must be a dedicated folder.' }
$setupDir = Join-Path $scratchParent ('setup-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $setupDir -Force | Out-Null
$savedEnv = @{}
foreach ($key in @('TEMP','TMP','UV_CACHE_DIR','PIP_CACHE_DIR','PYTHONDONTWRITEBYTECODE','UV_PYTHON_DOWNLOADS')) {
    $savedEnv[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
try {
    $env:TEMP = $setupDir
    $env:TMP = $setupDir
    $env:UV_CACHE_DIR = Join-Path $setupDir 'uv-cache'
    $env:PIP_CACHE_DIR = Join-Path $setupDir 'pip-cache'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:UV_PYTHON_DOWNLOADS = 'never'
    $venvDir = Join-Path $projectDir '.venv'
    if (-not (Test-Path -LiteralPath (Join-Path $venvDir 'Scripts\python.exe'))) {
        & uv venv --python $Python $venvDir
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11/3.12/3.13 required. Pass -Python with an installed Python executable.' }
    }
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    $lockFile = if ($WithTests) { 'requirements-test.lock.txt' } else { 'requirements.lock.txt' }
    & uv pip install --python $venvPython --require-hashes -r (Join-Path $projectDir $lockFile)
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & uv pip install --python $venvPython 'hatchling==1.27.0' 'editables==0.5'
    if ($LASTEXITCODE -ne 0) { throw 'Build backend installation failed.' }
    & uv pip install --python $venvPython --no-deps --no-build-isolation -e $projectDir
    if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
    Write-Host "Installed. Python: $venvPython"
    Write-Host 'Next: dot-source scripts\env.ps1, then run the smoke check in README.md.'
}
finally {
    foreach ($key in $savedEnv.Keys) {
        if ([string]::IsNullOrEmpty($savedEnv[$key])) { Remove-Item -LiteralPath "Env:$key" -ErrorAction SilentlyContinue }
        else { [Environment]::SetEnvironmentVariable($key,$savedEnv[$key],'Process') }
    }
    # Delete only the verified task-specific setup folder beneath the required temp root.
    $resolvedSetup = [IO.Path]::GetFullPath($setupDir)
    $allowedTemp = $scratchParent.TrimEnd('\') + [IO.Path]::DirectorySeparatorChar
    if ($resolvedSetup.StartsWith($allowedTemp, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedSetup -Recurse -Force
    }
}
