param(
    [Parameter(Mandatory=$true)][string]$OpenSimRoot,
    [Parameter(Mandatory=$true)][string]$TempRoot,
    [string]$BootstrapScript = '',
    [string]$UserDir = ''
)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($TempRoot)
if ($root -eq [IO.Path]::GetPathRoot($root) -or $root.StartsWith('\\')) { throw 'Use a dedicated local TempRoot folder.' }
$launcher=Join-Path $OpenSimRoot 'bin\OpenSim64.exe'
if (-not (Test-Path -LiteralPath $launcher)) { throw 'OpenSim64.exe not found.' }
if (($root+$launcher) -match '["\r\n]') { throw 'Invalid launcher or temporary path.' }
New-Item -ItemType Directory -Path $root -Force | Out-Null
if (-not $UserDir) { $UserDir=Join-Path (Split-Path -Parent $PSScriptRoot) 'state\gui-user' }
$profile=[IO.Path]::GetFullPath($UserDir)
if ($profile -eq [IO.Path]::GetPathRoot($profile) -or $profile.StartsWith('\\') -or $profile -match '["\r\n]') { throw 'Use a dedicated local GUI UserDir.' }
New-Item -ItemType Directory -Path $profile -Force | Out-Null
# Preferences and the first-launch marker are persistent application state.
# Route the GUI's var/log diagnostics to the caller's temporary root.
$varTarget=Join-Path $root 'gui-var'
New-Item -ItemType Directory -Path $varTarget -Force | Out-Null
$varLink=Join-Path $profile 'var'
if (-not (Test-Path -LiteralPath $varLink)) {
    New-Item -ItemType Junction -Path $varLink -Value $varTarget | Out-Null
}
elseif (-not ((Get-Item -LiteralPath $varLink -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'This UserDir contains an ordinary var folder. Choose a new dedicated UserDir so diagnostics remain under TempRoot.'
}
elseif ([IO.Path]::GetFullPath(@((Get-Item -LiteralPath $varLink -Force).Target)[0]).TrimEnd('\') -ine $varTarget.TrimEnd('\')) {
    throw 'This UserDir already sends logs to a different TempRoot. Use its original TempRoot or choose another dedicated UserDir.'
}
$oldTemp=$env:TEMP
$oldTmp=$env:TMP
try {
    $env:TEMP=$root
    $env:TMP=$root
    $arguments='--userdir "'+$profile+'" --cachedir "'+(Join-Path $root 'gui-cache')+'" -J-Djava.io.tmpdir="'+$root+'"'
    if($BootstrapScript) {
        $bootstrap=[IO.Path]::GetFullPath($BootstrapScript)
        if($bootstrap -match '["\r\n]' -or $bootstrap.StartsWith('\\')) {throw 'Use an absolute local bootstrap path.'}
        $arguments+=' -J-Dopensim.mcp.gui.bootstrap="'+$bootstrap+'"'
    }
    # This is the visible OpenSim application requested by the user.
    Start-Process -FilePath $launcher -ArgumentList $arguments -WorkingDirectory $OpenSimRoot
}
finally {
    $env:TEMP=$oldTemp
    $env:TMP=$oldTmp
}
