param([Parameter(Mandatory=$true)][string]$Archive,[Parameter(Mandatory=$true)][string]$SHA256,
      [Parameter(Mandatory=$true)][string]$Destination,[Parameter(Mandatory=$true)][string]$TempRoot,
      [string]$Config='', [string]$JournalRoot='', [switch]$Activate, [switch]$AllowWindowsServer)
$ErrorActionPreference='Stop'
$projectDir=Split-Path -Parent $PSScriptRoot
$server=Join-Path $projectDir '.venv\Scripts\python.exe'
$manager=Join-Path $PSScriptRoot 'manage_release.py'
& $server -B $manager extract --archive $Archive --sha256 $SHA256 --destination $Destination
if ($LASTEXITCODE -ne 0) { throw 'Release verification/extraction failed; existing installation was not changed.' }
& (Join-Path $Destination 'scripts\install.ps1') -TempRoot $TempRoot -SkipCodexRegistration -AllowWindowsServer:$AllowWindowsServer
if ($LASTEXITCODE -ne 0) { throw 'New environment failed validation. Existing Codex registration is unchanged.' }
if ($Activate) {
    if (-not $JournalRoot) { $JournalRoot=Join-Path $projectDir 'state\updates' }
    $arguments=@('activate','--project',$Destination,'--journal',$JournalRoot)
    if ($Config) { $arguments+=@('--config',$Config) }
    & $server -B $manager @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Activation failed; check the recovery journal.' }
}
else { Write-Host 'New release is ready. Run manage_release.py activate to switch after review.' }
