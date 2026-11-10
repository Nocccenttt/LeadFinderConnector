param(
    [string]$AppRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$SourceRoot,
    [string]$ConfigSource,
    [string]$PythonPath,
    [string]$ShortcutFolder = [Environment]::GetFolderPath('Desktop'),
    [switch]$SkipKeyPrompt,
    [switch]$NoLaunch
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'
$AppRoot = [IO.Path]::GetFullPath($AppRoot)
if ($env:LEADFINDER_NO_LAUNCH -eq '1') { $NoLaunch = $true }
if ($env:LEADFINDER_SKIP_KEY_PROMPT -eq '1') { $SkipKeyPrompt = $true }
if ($env:LEADFINDER_SHORTCUT_FOLDER) { $ShortcutFolder = $env:LEADFINDER_SHORTCUT_FOLDER }

function Invoke-Python([string]$Executable, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Executable @Arguments
    } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "A Python setup step failed (exit $LASTEXITCODE). Check the output above and retry setup." }
}

function Find-Python {
    $candidates = @()
    if ($PythonPath) { $candidates += $PythonPath }
    $candidates += (Join-Path (Split-Path -Parent $AppRoot) 'python\python.exe')
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike '*\WindowsApps\*') { $candidates += $command.Source }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $candidate) {
            $previous = $ErrorActionPreference
            try {
                $ErrorActionPreference = 'SilentlyContinue'
                & $candidate -c "import sys,struct,venv; sys.exit(0 if (3,11) <= sys.version_info[:2] < (3,15) and struct.calcsize('P')==8 else 1)" 2>$null
            } finally { $ErrorActionPreference = $previous }
            if ($LASTEXITCODE -eq 0) { return $candidate }
        }
    }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        $previous = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'SilentlyContinue'
            $found = & $py.Source -3 -c "import sys,struct,venv; sys.exit(1) if not ((3,11) <= sys.version_info[:2] < (3,15) and struct.calcsize('P')==8) else print(sys.executable)" 2>$null
        } finally { $ErrorActionPreference = $previous }
        if ($LASTEXITCODE -eq 0 -and $found) { return [string]$found }
    }
    return $null
}

function Set-UpKeys {
    $config = Join-Path $AppRoot '.env'
    if (!(Test-Path -LiteralPath $config)) {
        if ($ConfigSource -and (Test-Path -LiteralPath $ConfigSource)) {
            Copy-Item -LiteralPath $ConfigSource -Destination $config
            Write-Host 'Imported the supplied .env file.'
            return
        }
        Copy-Item -LiteralPath (Join-Path $AppRoot '.env.example') -Destination $config
    } else { return }
    if ($SkipKeyPrompt) { return }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $form = New-Object Windows.Forms.Form
    $form.Text = 'LeadFinder - API keys'
    $form.ClientSize = New-Object Drawing.Size(460,350)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.Font = New-Object Drawing.Font('Segoe UI',10)
    $intro = New-Object Windows.Forms.Label
    $intro.Text = "Enter the keys you were provided. These stay on this computer.`r`nYou can also open the app now and add them to .env later."
    $intro.SetBounds(20,15,420,55)
    $form.Controls.Add($intro)
    $inputs = @{}
    $names = @('GOOGLE_MAPS_API_KEY','DEEPSEEK_API_KEY','PEXELS_API_KEY')
    $labels = @('Google Maps API key','DeepSeek API key','Pexels API key (optional images)')
    for ($index=0; $index -lt $names.Count; $index++) {
        $label = New-Object Windows.Forms.Label
        $label.Text = $labels[$index]
        $label.SetBounds(20,(76+$index*66),420,22)
        $inputBox = New-Object Windows.Forms.TextBox
        $inputBox.UseSystemPasswordChar = $true
        $inputBox.SetBounds(20,(100+$index*66),420,27)
        $inputs[$names[$index]] = $inputBox
        $form.Controls.AddRange(@($label,$inputBox))
    }
    $save = New-Object Windows.Forms.Button
    $save.Text = 'Save and open'
    $save.SetBounds(290,300,150,34)
    $save.Add_Click({
        $lines = foreach ($name in $names) {
            $value = $inputs[$name].Text.Trim()
            if ($value -match '[\r\n"''\\]') {
                [Windows.Forms.MessageBox]::Show('Paste the API key only, without quotes or extra lines.','Check API key') | Out-Null
                return
            }
            "$name='$value'"
        }
        [IO.File]::WriteAllLines($config,[string[]]$lines,(New-Object Text.UTF8Encoding($false)))
        $form.Close()
    })
    $form.Controls.Add($save)
    $form.AcceptButton = $save
    $form.ShowDialog() | Out-Null
    $form.Dispose()
}

function Stop-IdleWorkspace {
    $pidFile = Join-Path $AppRoot 'logs\dashboard.pid'
    if (!(Test-Path -LiteralPath $pidFile)) { return }
    $serverId = 0
    if (![int]::TryParse((Get-Content -LiteralPath $pidFile -Raw).Trim(),[ref]$serverId)) { return }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $serverId"
    $entrypoint = Join-Path $AppRoot 'scripts\launch_dashboard.py'
    if (!$process -or $process.CommandLine.IndexOf(('"'+$entrypoint+'"'),[StringComparison]::OrdinalIgnoreCase) -lt 0) { return }
    $port = (Get-Content -LiteralPath (Join-Path $AppRoot 'logs\dashboard.port') -Raw).Trim()
    $session = Invoke-RestMethod -UseBasicParsing -Uri "http://127.0.0.1:$port/session" -TimeoutSec 3
    if (@($session.active_jobs).Count -gt 0) { throw 'A search or build is running. Let it finish before updating LeadFinder.' }
    Write-Host 'Closing the idle app to install this update...'
    & (Join-Path $PSScriptRoot 'Stop-LeadFinder.ps1') -AppRoot $AppRoot
}

try {
    if ($SourceRoot) {
        $SourceRoot = [IO.Path]::GetFullPath($SourceRoot)
        $destination = if ($env:LEADFINDER_INSTALL_ROOT) { $env:LEADFINDER_INSTALL_ROOT } else { Join-Path $env:LOCALAPPDATA 'LeadFinder' }
        $AppRoot = [IO.Path]::GetFullPath((Join-Path $destination 'app'))
        Stop-IdleWorkspace
        if ($AppRoot -ne $SourceRoot) {
            Write-Host '[1/5] Installing LeadFinder from your extracted ZIP...'
            New-Item -ItemType Directory -Force -Path $AppRoot | Out-Null
            Get-ChildItem -LiteralPath $SourceRoot -File | Where-Object { $_.Extension -eq '.py' -or $_.Name -in @('requirements.txt','.env.example','START_LEADFINDER.bat','STOP_LEADFINDER.bat','DOWNLOAD_LEADFINDER.bat') } | Copy-Item -Destination $AppRoot -Force
            foreach ($folder in @('assets','static','templates','scripts')) {
                Copy-Item -LiteralPath (Join-Path $SourceRoot $folder) -Destination $AppRoot -Recurse -Force
            }
        }
    }
    if (!$SourceRoot) { Stop-IdleWorkspace }
    if (![Environment]::Is64BitOperatingSystem) { throw 'LeadFinder requires 64-bit Windows 10 or Windows 11.' }
    Write-Host '[2/5] Preparing Python...'
    $python = Find-Python
    if (!$python) {
        $version = '3.13.17'
        $architecture = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') { 'arm64' } else { 'amd64' }
        $runtime = Join-Path (Split-Path -Parent $AppRoot) 'python'
        $installer = Join-Path $env:TEMP ("LeadFinder-python-"+[guid]::NewGuid().ToString('N')+'.exe')
        try {
            Write-Host 'Downloading Python from python.org (no administrator access needed)...'
            Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/$version/python-$version-$architecture.exe" -OutFile $installer -TimeoutSec 300
            $signature = Get-AuthenticodeSignature -LiteralPath $installer
            if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'The downloaded Python installer could not be verified.' }
            $process = Start-Process -FilePath $installer -ArgumentList @('/quiet','InstallAllUsers=0',"TargetDir=`"$runtime`"",'PrependPath=0','Include_launcher=0','Include_test=0','Include_pip=1','Shortcuts=0') -WindowStyle Hidden -PassThru -Wait
            if ($process.ExitCode -notin @(0,3010)) { throw "Python installation failed (exit $($process.ExitCode))." }
            $python = Join-Path $runtime 'python.exe'
        } finally {
            if (Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer -Force }
        }
    }
    Invoke-Python $python @('-m','venv',(Join-Path $AppRoot '.venv'))
    $venvPython = Join-Path $AppRoot '.venv\Scripts\python.exe'
    Write-Host '[3/5] Installing application packages...'
    Invoke-Python $venvPython @('-m','pip','install','--disable-pip-version-check','-r',(Join-Path $AppRoot 'requirements.txt'))
    Write-Host '[4/5] Installing the browser used for design references...'
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Split-Path -Parent $AppRoot) 'browsers'
    Invoke-Python $venvPython @('-m','playwright','install','chromium')
    Invoke-Python $venvPython @('-c','import flask,openai,dotenv,bs4,requests,playwright')
    Write-Host '[5/5] Saving settings and creating your launcher...'
    Set-UpKeys
    New-Item -ItemType Directory -Force -Path (Join-Path $AppRoot 'codex_handoffs') | Out-Null
    New-Item -ItemType Directory -Force -Path $ShortcutFolder | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $ShortcutFolder 'LeadFinder.lnk'))
    $shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$(Join-Path $AppRoot 'scripts\Start-LeadFinder.ps1')`""
    $shortcut.WorkingDirectory = $AppRoot
    $shortcut.Description = 'Open LeadFinder'
    $shortcut.Save()
    @{ installed_at=(Get-Date).ToString('o'); python=$venvPython } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $AppRoot '.installed.json') -Encoding UTF8
    Write-Host 'Setup complete. Next time, double-click the LeadFinder shortcut on your desktop.'
    if (!$NoLaunch) { & (Join-Path $AppRoot 'scripts\Start-LeadFinder.ps1') }
    exit 0
} catch {
    Write-Host "Setup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
