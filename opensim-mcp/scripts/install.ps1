param(
    [string]$TempRoot = '',
    [string]$OpenSimRoot = '',
    [switch]$SkipCodexRegistration,
    [switch]$WithTests,
    [switch]$Repair,
    [switch]$SkipNativeSmoke,
    [switch]$Offline,
    [switch]$AllowWindowsServer
)
$ErrorActionPreference = 'Stop'
$projectDir = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$osInfo = Get-CimInstance Win32_OperatingSystem
if (-not [Environment]::Is64BitOperatingSystem -or [int]$osInfo.BuildNumber -lt 22000 -or ($osInfo.ProductType -ne 1 -and -not $AllowWindowsServer)) {
    throw 'Requires Windows 11 x64. Windows Server is only allowed for CI with -AllowWindowsServer.'
}
if (-not $TempRoot) {
    if (Test-Path -LiteralPath 'E:\') { $TempRoot = 'E:\simulink\_codex_tmp\opensim-mcp-runtime' }
    else { $TempRoot = Join-Path ([IO.Path]::GetTempPath()) 'opensim-mcp' }
}
$scratchParent = [IO.Path]::GetFullPath($TempRoot).TrimEnd('\')
if ($scratchParent -eq [IO.Path]::GetPathRoot($scratchParent).TrimEnd('\')) { throw 'TempRoot must be a dedicated folder.' }
if ($scratchParent.StartsWith($projectDir+'\',[StringComparison]::OrdinalIgnoreCase) -or $scratchParent -eq $projectDir) { throw 'Temporary files must be outside the project.' }
$stage = Join-Path $scratchParent ('install-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$savedEnv=@{}
foreach ($key in @('TEMP','TMP','PATH','UV_CACHE_DIR','PIP_CACHE_DIR','UV_PYTHON_INSTALL_DIR','UV_PYTHON_BIN_DIR','UV_PYTHON_DOWNLOADS','UV_OFFLINE','UV_NO_CONFIG','PYTHONDONTWRITEBYTECODE','PYTHONUTF8')) {
    $savedEnv[$key]=[Environment]::GetEnvironmentVariable($key,'Process')
}
try {
    $env:TEMP=$stage; $env:TMP=$stage
    $env:UV_CACHE_DIR=Join-Path $scratchParent 'dependency-cache'; $env:PIP_CACHE_DIR=Join-Path $scratchParent 'pip-cache'
    $env:UV_PYTHON_INSTALL_DIR=Join-Path $projectDir 'runtimes\python'
    $env:UV_PYTHON_BIN_DIR=Join-Path $projectDir 'runtimes\bin'
    $env:UV_PYTHON_DOWNLOADS='auto'; $env:UV_NO_CONFIG='1'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONUTF8='1'
    if ($Offline) { $env:UV_OFFLINE='1';$env:UV_PYTHON_DOWNLOADS='never' }
    $uv=Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        $tools=Join-Path $projectDir 'runtimes\tools'; New-Item -ItemType Directory -Path $tools -Force | Out-Null
        $uvPath=Join-Path $tools 'uv.exe'
        if (-not (Test-Path -LiteralPath $uvPath)) {
            if ($Offline) { throw 'Offline installation requires an existing uv, managed Python and populated dependency cache. Perform one online install first; no Codex settings were changed.' }
            Write-Host 'Downloading pinned uv 0.11.26 from the official GitHub release...'
            $archive=Join-Path $stage 'uv.zip'
            [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/astral-sh/uv/releases/download/0.11.26/uv-x86_64-pc-windows-msvc.zip' -OutFile $archive
            $sha=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($sha -ne '4e1278ede866be6c0bf32d2f466cc6de7a9fb399ecf20c9ce2d186e52424be47') { throw 'uv archive SHA256 mismatch.' }
            $unpacked=Join-Path $stage 'uv'; Expand-Archive -LiteralPath $archive -DestinationPath $unpacked
            $binary=Get-ChildItem -LiteralPath $unpacked -Filter uv.exe -Recurse | Select-Object -First 1
            if (-not $binary) { throw 'uv executable missing from verified archive.' }
            Copy-Item -LiteralPath $binary.FullName -Destination $uvPath
        }
        $env:PATH=$tools+';'+$env:PATH
    }
    Write-Host 'Preparing CPython 3.12.13 x64 and isolated API environment...'
    & uv python install 3.12.13 --no-bin
    if ($LASTEXITCODE -ne 0) { throw 'Python download/install failed.' }
    & uv venv --python 3.12.13 (Join-Path $projectDir '.venv') --allow-existing
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare server environment.' }
    $server=Join-Path $projectDir '.venv\Scripts\python.exe'
    & $server -B -c 'import sys; assert sys.version_info[:2]==(3,12) and sys.maxsize>2**32'
    if ($LASTEXITCODE -ne 0) { throw 'Existing server environment requires CPython 3.12 x64. Preserve it and reinstall in a fresh release folder.' }
    $lock=if ($WithTests) {'requirements-test.lock.txt'} else {'requirements.lock.txt'}
    $installArgs=@('pip','install','--python',$server,'--require-hashes','-r',(Join-Path $projectDir $lock))
    if ($Repair) { $installArgs+='--reinstall' }
    & uv @installArgs
    if ($LASTEXITCODE -ne 0) { throw 'Server dependencies failed. Close Codex if existing package files are locked.' }
    # The editable install uses the pinned Hatchling backend declared in
    # pyproject.toml. Install it into the managed environment first so the
    # final step also works with an offline cache and does not create a
    # second isolated build environment.
    $buildBackends = @('hatchling==1.27.0', 'editables==0.5')
    & uv pip install --python $server @buildBackends
    if ($LASTEXITCODE -ne 0) { throw 'Build backend installation failed. Check the dependency cache or network access.' }
    & uv pip install --python $server --no-deps --no-build-isolation -e $projectDir
    if ($LASTEXITCODE -ne 0) { throw 'Adapter install failed.' }
    $apiDir=Join-Path $projectDir '.api46-venv'
    & uv venv --python 3.12.13 $apiDir --allow-existing
    if ($LASTEXITCODE -ne 0) { throw 'API environment failed.' }
    $api=Join-Path $apiDir 'Scripts\python.exe'
    $apiArgs=@('pip','install','--python',$api,'--require-hashes','-r',(Join-Path $projectDir 'requirements-api46.lock.txt'))
    if ($Repair) { $apiArgs+='--reinstall' }
    & uv @apiArgs
    if ($LASTEXITCODE -ne 0) { throw 'OpenSim API pinned dependency install failed.' }
    Push-Location $stage
    try { & $api -B -c 'import opensim; print(opensim.GetVersionAndDate())' }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw 'Native API import failed. Check the x64 Visual C++ runtime and doctor instructions.' }
    $results=Join-Path $projectDir 'results'; New-Item -ItemType Directory -Path $results -Force | Out-Null
    $block=Join-Path $projectDir 'config\opensim_mcp.generated.toml'
    $configText=& (Join-Path $PSScriptRoot 'print-codex-config.ps1') -TempRoot $scratchParent -OpenSimRoot $OpenSimRoot
    [IO.File]::WriteAllText($block,($configText -join "`n"),(New-Object Text.UTF8Encoding($false)))
    . (Join-Path $PSScriptRoot 'env.ps1') -TempRoot $scratchParent -OpenSimRoot $OpenSimRoot
    if (-not $SkipNativeSmoke) {
        Write-Host 'Running the bundled native IK and MCP smoke check...'
        $smokeLog=Join-Path $scratchParent ('install-smoke-'+[guid]::NewGuid().ToString('N')+'.log')
        # Windows PowerShell 5.1 treats redirected native stderr as ErrorRecords.
        # Drain both streams directly so normal MCP diagnostics cannot abort setup.
        $startInfo=New-Object Diagnostics.ProcessStartInfo
        $startInfo.FileName=$server
        $startInfo.Arguments='-B "'+(Join-Path $PSScriptRoot 'smoke_mcp.py')+'" --examples "'+(Join-Path $projectDir 'examples')+'" --run-ik'
        $startInfo.UseShellExecute=$false; $startInfo.CreateNoWindow=$true
        $startInfo.RedirectStandardOutput=$true; $startInfo.RedirectStandardError=$true
        $startInfo.StandardOutputEncoding=[Text.Encoding]::UTF8; $startInfo.StandardErrorEncoding=[Text.Encoding]::UTF8
        $smokeProcess=New-Object Diagnostics.Process
        $smokeProcess.StartInfo=$startInfo
        try {
            [void]$smokeProcess.Start()
            $outputTask=$smokeProcess.StandardOutput.ReadToEndAsync()
            $errorTask=$smokeProcess.StandardError.ReadToEndAsync()
            if (-not $smokeProcess.WaitForExit(240000)) { $smokeProcess.Kill(); throw 'Installation MCP self-check exceeded 240 seconds.' }
            $smokeExit=$smokeProcess.ExitCode
            [IO.File]::WriteAllText($smokeLog,($outputTask.Result+"`n"+$errorTask.Result),(New-Object Text.UTF8Encoding($false)))
        }
        finally { $smokeProcess.Dispose() }
        if ($smokeExit -ne 0) { Get-Content -LiteralPath $smokeLog -Tail 25; throw "Native/MCP smoke test failed. Log: $smokeLog" }
        Write-Host "Native MCP/IK passed. Log: $smokeLog"
        $startInfo.FileName=$api
        $startInfo.Arguments='-B "'+(Join-Path $projectDir 'src\opensim_mcp\tool_runner.py')+'" --solver-probe'
        $startInfo.WorkingDirectory=$stage
        $solverProcess=New-Object Diagnostics.Process; $solverProcess.StartInfo=$startInfo
        $solverLog=Join-Path $scratchParent ('solver-probe-'+[guid]::NewGuid().ToString('N')+'.log')
        try {
            [void]$solverProcess.Start();$solverOut=$solverProcess.StandardOutput.ReadToEndAsync();$solverErr=$solverProcess.StandardError.ReadToEndAsync()
            if (-not $solverProcess.WaitForExit(60000)) { $solverProcess.Kill();throw 'Native Moco solver probe exceeded 60 seconds.' }
            $solverExit=$solverProcess.ExitCode
            [IO.File]::WriteAllText($solverLog,($solverOut.Result+"`n"+$solverErr.Result),(New-Object Text.UTF8Encoding($false)))
        } finally { $solverProcess.Dispose() }
        if ($solverExit -ne 0) { throw "Native Moco/IPOPT solver probe failed; existing Codex registration retained. Log: $solverLog" }
        Write-Host "Native Moco/IPOPT solve passed. Log: $solverLog"
    }
    # Publish integrations only after the actual native checks passed.
    if ($OpenSimRoot) {
        & (Join-Path $projectDir 'gui-autobridge\install-autobridge.ps1') -OpenSimRoot $OpenSimRoot -BootstrapScript (Join-Path $scratchParent 'gui-bridge\start_gui_bridge.py')
        if ($LASTEXITCODE -ne 0) { throw 'GUI bridge install failed; existing Codex registration retained.' }
    }
    if (-not $SkipCodexRegistration) {
        & $server -B (Join-Path $PSScriptRoot 'register_codex.py') --block $block --backup-dir (Join-Path $projectDir 'state\codex-config-backups')
        if ($LASTEXITCODE -ne 0) { throw 'Codex registration could not preserve the existing TOML. Use the generated block manually.' }
    }
    Write-Host "Ready. Codex server: opensim_mcp. Restart Codex once. Generated configuration: $block"
}
finally {
    foreach ($key in $savedEnv.Keys) { [Environment]::SetEnvironmentVariable($key,$savedEnv[$key],'Process') }
    $resolved=[IO.Path]::GetFullPath($stage)
    if ($resolved.StartsWith($scratchParent+'\',[StringComparison]::OrdinalIgnoreCase)) {
        try { Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction Stop }
        catch { Write-Warning "Temporary installation folder could not be removed: $resolved" }
    }
}
