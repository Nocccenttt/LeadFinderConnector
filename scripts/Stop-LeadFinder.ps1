param([string]$AppRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$AppRoot = [IO.Path]::GetFullPath($AppRoot)
$pidFile = Join-Path $AppRoot 'logs\dashboard.pid'
if (!(Test-Path -LiteralPath $pidFile)) { exit 0 }
$serverId = 0
if (![int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(),[ref]$serverId)) { throw 'The saved server process ID is invalid.' }
$process = Get-CimInstance Win32_Process -Filter "ProcessId = $serverId"
# A stale PID must never stop an unrelated application.
$entrypoint = Join-Path $AppRoot 'scripts\launch_dashboard.py'
if ($process -and $process.Name -match '^python(w)?\.exe$' -and $process.CommandLine.IndexOf(('"'+$entrypoint+'"'),[StringComparison]::OrdinalIgnoreCase) -ge 0) {
    # Windows virtual-environment launchers can own a child Python process.
    & "$env:SystemRoot\System32\taskkill.exe" /PID $serverId /T /F | Out-Null
    Remove-Item -LiteralPath $pidFile -Force
}
