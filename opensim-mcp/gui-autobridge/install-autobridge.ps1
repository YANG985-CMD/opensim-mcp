[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [Parameter(Mandatory=$true)][string]$OpenSimRoot,
    [string]$BootstrapScript,
    [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'
$cluster = Join-Path ([IO.Path]::GetFullPath($OpenSimRoot)) 'opensim'
if (-not (Test-Path -LiteralPath (Join-Path $cluster 'modules\org-opensim-console.jar'))) {
    throw 'An installed OpenSim GUI with scripting support is required.'
}
$module = Join-Path $cluster 'modules\org-opensim-mcp-autobridge.jar'
$properties = Join-Path $cluster 'modules\org-opensim-mcp-autobridge.properties'
$registration = Join-Path $cluster 'config\Modules\org-opensim-mcp-autobridge.xml'
if ($Uninstall) {
    foreach ($path in @($registration,$properties,$module)) {
        if ((Test-Path -LiteralPath $path) -and $PSCmdlet.ShouldProcess($path,'Remove MCP startup plugin file')) {
            Remove-Item -LiteralPath $path -Force
        }
    }
    Write-Host 'MCP startup plugin removed. Restart OpenSim.'
    return
}
$source = Join-Path $PSScriptRoot 'dist\org-opensim-mcp-autobridge.jar'
if (-not (Test-Path -LiteralPath $source)) { throw 'Build the plugin first, or use the release ZIP with its prebuilt JAR.' }
if (-not $BootstrapScript -or -not [IO.Path]::IsPathRooted($BootstrapScript) -or $BootstrapScript.StartsWith('\\') -or $BootstrapScript -match "[\r\n]" -or -not $BootstrapScript.EndsWith('.py')) {
    throw 'Pass the absolute local bootstrap_script path returned by connect_gui.'
}
$bootstrap = [IO.Path]::GetFullPath($BootstrapScript).Replace('\','/')
if ($PSCmdlet.ShouldProcess($cluster,'Install OpenSim MCP startup plugin')) {
    Copy-Item -LiteralPath $source -Destination $module -Force
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($properties, ("bootstrap=$bootstrap" + [Environment]::NewLine), $utf8)
    $xml = @'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE module PUBLIC "-//NetBeans//DTD Module Status 1.0//EN"
                        "http://www.netbeans.org/dtds/module-status-1_0.dtd">
<module name="org.opensim.mcp.autobridge">
    <param name="autoload">false</param>
    <param name="eager">false</param>
    <param name="enabled">true</param>
    <param name="jar">modules/org-opensim-mcp-autobridge.jar</param>
    <param name="reloadable">false</param>
</module>
'@
    [IO.File]::WriteAllText($registration, $xml, $utf8)
}
Write-Host 'MCP startup plugin installed. Restart OpenSim; the bridge attaches automatically.'
