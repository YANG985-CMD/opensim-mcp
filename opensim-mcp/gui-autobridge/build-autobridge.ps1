param(
    [Parameter(Mandatory=$true)][string]$OpenSimRoot,
    [Parameter(Mandatory=$true)][string]$JdkHome,
    [Parameter(Mandatory=$true)][string]$TempRoot
)
$ErrorActionPreference = 'Stop'
$javac = Join-Path $JdkHome 'bin\javac.exe'
$jar = Join-Path $JdkHome 'bin\jar.exe'
if (-not (Test-Path -LiteralPath $javac)) { throw 'A JDK with javac.exe is required to build the plugin.' }
$scratch = [IO.Path]::GetFullPath($TempRoot).TrimEnd('\')
if ($scratch -eq [IO.Path]::GetPathRoot($scratch)) { throw 'Use a dedicated TempRoot folder.' }
$stage = Join-Path $scratch ('autobridge-build-' + [guid]::NewGuid().ToString('N'))
$classes = Join-Path $stage 'classes'
New-Item -ItemType Directory -Path $classes -Force | Out-Null
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
try {
    $env:TEMP = $stage
    $env:TMP = $stage
    $jars = @(foreach ($relative in @('platform\modules','platform\lib','opensim\modules','opensim\modules\ext')) {
        Get-ChildItem -LiteralPath (Join-Path $OpenSimRoot $relative) -Filter '*.jar' -ErrorAction SilentlyContinue | ForEach-Object FullName
    })
    if (-not ($jars | Where-Object { $_ -like '*org-opensim-console.jar' })) { throw 'OpenSim GUI scripting module not found.' }
    $sources = @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'src') -Recurse -Filter '*.java' | ForEach-Object FullName)
    & $javac -proc:none -encoding UTF-8 -source 8 -target 8 -cp ($jars -join ';') -d $classes $sources
    if ($LASTEXITCODE -ne 0) { throw 'javac failed.' }
    $outputDir = Join-Path $PSScriptRoot 'dist'
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    $output = Join-Path $outputDir 'org-opensim-mcp-autobridge.jar'
    & $jar cfm $output (Join-Path $PSScriptRoot 'manifest.mf') -C $classes .
    if ($LASTEXITCODE -ne 0) { throw 'jar failed.' }
    Write-Output $output
}
finally {
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $resolvedStage = [IO.Path]::GetFullPath($stage)
    if ($resolvedStage.StartsWith($scratch + '\',[StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}
