param(
    [string]$AppRoot = (Split-Path -Parent $PSScriptRoot),
    [int]$Port = 3000,
    [ValidateRange(1,300)][int]$StartupTimeoutSeconds = 60,
    [switch]$NoBrowser,
    [switch]$NoDialogs
)
$ErrorActionPreference = 'Stop'
$AppRoot = [IO.Path]::GetFullPath($AppRoot)
$explicitPort = $PSBoundParameters.ContainsKey('Port')
$logs = Join-Path $AppRoot 'logs'
$pidFile = Join-Path $logs 'dashboard.pid'
$portFile = Join-Path $logs 'dashboard.port'
if (!$explicitPort -and (Test-Path -LiteralPath $portFile)) {
    $savedPort = 0
    if ([int]::TryParse((Get-Content -LiteralPath $portFile -Raw).Trim(),[ref]$savedPort) -and $savedPort -gt 1024 -and $savedPort -le 65535) { $Port = $savedPort }
}
$address = "http://127.0.0.1:$Port"
$lock = $null
$ownsLock = $false
$server = $null

function Get-Workspace {
    try { return Invoke-RestMethod -UseBasicParsing -Uri "$address/health" -TimeoutSec 2 } catch { return $null }
}
function Open-Workspace {
    if (!$NoBrowser) { Start-Process $address }
    Write-Output "LeadFinder is ready at $address"
}
function Stop-FailedStart {
    if (!$server) { return }
    try {
        $server.Refresh()
        if (!$server.HasExited) {
            $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($server.Id)"
            $entrypoint = Join-Path $AppRoot 'scripts\launch_dashboard.py'
            # Check the process we launched, not an unrelated process reusing its PID.
            if (!$current -or $current.Name -notmatch '^python(w)?\.exe$' -or !$current.CommandLine -or
                $current.CommandLine.IndexOf(('"'+$entrypoint+'"'),[StringComparison]::OrdinalIgnoreCase) -lt 0 -or
                !$current.CreationDate -or [Math]::Abs(($current.CreationDate.ToUniversalTime() - $server.StartTime.ToUniversalTime()).TotalMilliseconds) -gt 1) { return }
            $server.Refresh()
            if (!$server.HasExited) {
                & "$env:SystemRoot\System32\taskkill.exe" /PID $server.Id /T /F 2>$null | Out-Null
                if ($LASTEXITCODE -ne 0) { return }
            }
        }
        if ((Test-Path -LiteralPath $pidFile) -and (Get-Content -LiteralPath $pidFile -Raw).Trim() -eq [string]$server.Id) {
            Remove-Item -LiteralPath $pidFile -Force
        }
    } catch { # Keep the original startup error; a retained PID still allows Stop to retry.
    }
}

try {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { $identity = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($AppRoot.ToLowerInvariant()))).Replace('-','') } finally { $hash.Dispose() }
    $lock = New-Object Threading.Mutex($false,"Local\LeadFinder-$identity")
    try { $ownsLock = $lock.WaitOne(60000) } catch [Threading.AbandonedMutexException] { $ownsLock = $true }
    if (!$ownsLock) { throw 'Another LeadFinder launch is still starting. Try opening it again in a moment.' }
    for ($candidate=0; $candidate -lt 20; $candidate++) {
        $current = Get-Workspace
        if ($current -and $current.app -eq 'leadfinder' -and $current.root -eq $AppRoot) { Open-Workspace; exit 0 }
        $connection = New-Object Net.Sockets.TcpClient
        try {
            $attempt = $connection.BeginConnect('127.0.0.1',$Port,$null,$null)
            $occupied = $attempt.AsyncWaitHandle.WaitOne(500) -and $connection.Connected
        } finally { $connection.Dispose() }
        if (!$occupied) { break }
        if ($explicitPort) { throw "Port $Port is already used by another application or LeadFinder workspace." }
        $Port += 1
        if ($Port -gt 65535) { $Port = 3000 }
        $address = "http://127.0.0.1:$Port"
    }
    if ($occupied) { throw 'No available local port was found. Close an unused workspace and try again.' }
    $python = Join-Path $AppRoot '.venv\Scripts\pythonw.exe'
    if (!(Test-Path -LiteralPath $python)) { throw 'LeadFinder setup is incomplete. Run the installer again to install the required files.' }
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    $env:PYTHONUTF8 = '1'
    $env:LEADFINDER_PORT = [string]$Port
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Split-Path -Parent $AppRoot) 'browsers'
    $server = Start-Process -FilePath $python -ArgumentList @('-u',"`"$(Join-Path $AppRoot 'scripts\launch_dashboard.py')`"") -WorkingDirectory $AppRoot -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $pidFile -Value $server.Id
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    do {
        Start-Sleep -Milliseconds 250
        $server.Refresh()
        if ($server.HasExited) { throw "LeadFinder could not start. Details are in $logs\dashboard.err.log. Run the installer again if packages are missing." }
        $current = Get-Workspace
        if ($current -and $current.app -eq 'leadfinder' -and $current.root -eq $AppRoot) {
            Set-Content -LiteralPath $portFile -Value $Port
            Open-Workspace
            exit 0
        }
    } while ((Get-Date) -lt $deadline)
    throw "LeadFinder did not become ready within $StartupTimeoutSeconds seconds. Details are in $logs\dashboard.err.log."
} catch {
    $message = $_.Exception.Message
    Stop-FailedStart
    if (!$NoDialogs) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($message,'LeadFinder could not open',[Windows.Forms.MessageBoxButtons]::OK,[Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    }
    Write-Error $message
    exit 1
} finally {
    if ($ownsLock) { $lock.ReleaseMutex() }
    if ($lock) { $lock.Dispose() }
}
