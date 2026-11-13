param(
    [string]$Python = 'py',
    [string]$TypeLibrary,
    [string]$OutputRoot = (Join-Path $PSScriptRoot 'outputs'),
    [string]$RuntimeRoot = (Join-Path ([System.IO.Path]::GetTempPath()) 'solidworks-mcp-v0.5.3')
)

$ErrorActionPreference = 'Stop'
if (-not $TypeLibrary) {
    $setup = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\SolidWorks\SOLIDWORKS 2025\Setup' -ErrorAction SilentlyContinue
    $candidates = @()
    if ($setup -and $setup.'SolidWorks Folder') {
        $candidates += Join-Path $setup.'SolidWorks Folder' 'sldworks.tlb'
    }
    $candidates += Join-Path $env:ProgramFiles 'SOLIDWORKS Corp\SOLIDWORKS\sldworks.tlb'
    $TypeLibrary = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $TypeLibrary) {
        throw 'SOLIDWORKS 2025 type library was not found. Use -TypeLibrary with the local sldworks.tlb path.'
    }
}

$library = Get-Item -LiteralPath $TypeLibrary
if ($library.PSIsContainer -or $library.Name -ine 'sldworks.tlb') {
    throw 'TypeLibrary must point to the installed SOLIDWORKS 2025 sldworks.tlb file.'
}

$versionCheck = "import sys,struct; assert sys.platform=='win32' and sys.implementation.name=='cpython' and sys.version_info[:2]==(3,12) and struct.calcsize('P')==8, 'Windows x64 CPython 3.12 is required'"
$launcherArgs = @()
if ($Python -eq 'py' -or $Python -eq 'py.exe') {
    if (Get-Command 'py.exe' -ErrorAction SilentlyContinue) {
        $launcherArgs = @('-3.12')
    } else {
        $Python = 'python.exe'
    }
}
& $Python @launcherArgs -B -c $versionCheck
if ($LASTEXITCODE -ne 0) { throw 'Install Windows x64 CPython 3.12 or pass -Python with its executable path.' }

$runtime = (New-Item -ItemType Directory -Path $RuntimeRoot -Force).FullName
$env:TEMP = $runtime
$env:TMP = $runtime
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$venv = Join-Path $PSScriptRoot '.venv'
$clientPython = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $clientPython -PathType Leaf)) {
    & $Python @launcherArgs -B -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
}
& $clientPython -B -c $versionCheck
if ($LASTEXITCODE -ne 0) { throw 'The existing .venv is incompatible. Reinstall from a freshly extracted package.' }

$wheelhouse = Join-Path $PSScriptRoot 'wheels'
$sourceArgs = @()
if (Test-Path -LiteralPath $wheelhouse -PathType Container) {
    $sourceArgs = @('--no-index', '--find-links', $wheelhouse)
}
& $clientPython -B -m pip install --no-cache-dir --disable-pip-version-check --only-binary=:all: @sourceArgs -r (Join-Path $PSScriptRoot 'requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check access to the Python package index.' }
& $clientPython -B -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Python dependency check failed.' }

$checkTypeLib = "from comtypes import typeinfo; import sys; t=typeinfo.LoadTypeLibEx(sys.argv[1],typeinfo.REGKIND_NONE).GetLibAttr(); assert t.wMajorVerNum == 33, f'Expected SOLIDWORKS 2025 type library version 33, got {t.wMajorVerNum}'"
& $clientPython -B -c $checkTypeLib $library.FullName
if ($LASTEXITCODE -ne 0) { throw 'The selected type library could not be verified as SOLIDWORKS 2025.' }

& $clientPython -B (Join-Path $PSScriptRoot 'configure.py') $library.FullName $OutputRoot $runtime
if ($LASTEXITCODE -ne 0) { throw 'Could not generate local MCP configuration files.' }
& $clientPython -B (Join-Path $PSScriptRoot 'diagnose.py')
if ($LASTEXITCODE -ne 0) { throw 'Local MCP self-test failed. Check the status above before registering it in Codex.' }
Write-Output 'Ready: mcp-codex.toml and mcp-harness.json'
