@echo off
setlocal
title Install LeadFinder
set "LEADFINDER_SETUP_FILE=%~f0"
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -Command "$text=[IO.File]::ReadAllText($env:LEADFINDER_SETUP_FILE); $marker='#'+' LEADFINDER_SETUP'; & ([scriptblock]::Create($text.Substring($text.IndexOf($marker)+$marker.Length)))"
if errorlevel 1 (
    echo.
    echo Setup could not finish. The error is shown above. Run this file again to retry.
    pause
    exit /b 1
)
exit /b 0
# LEADFINDER_SETUP
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'
$installRoot = if ($env:LEADFINDER_INSTALL_ROOT) { $env:LEADFINDER_INSTALL_ROOT } else { Join-Path $env:LOCALAPPDATA 'LeadFinder' }
$installRoot = [IO.Path]::GetFullPath($installRoot)
$appRoot = Join-Path $installRoot 'app'
$staging = $null
try {
    Write-Host 'LeadFinder setup - downloads the app, Python if needed, packages and Chromium.'
    Write-Host "Install location: $installRoot"
    $launcher = Join-Path $appRoot 'scripts\Start-LeadFinder.ps1'
    if ((Test-Path (Join-Path $appRoot '.installed.json')) -and (Test-Path (Join-Path $appRoot '.venv\Scripts\pythonw.exe')) -and (Test-Path $launcher)) {
        $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $installRoot 'browsers'
        $previous = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'SilentlyContinue'
            & (Join-Path $appRoot '.venv\Scripts\python.exe') -c 'import flask,openai,dotenv,bs4,requests,os; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); assert os.path.isfile(p.chromium.executable_path); p.stop()' 2>$null
        } finally { $ErrorActionPreference = $previous }
        if ($LASTEXITCODE -eq 0) {
            Write-Host 'LeadFinder is already installed.'
            if ($env:LEADFINDER_NO_LAUNCH -ne '1') { & $launcher }
            exit 0
        }
        Write-Host 'Repairing missing application components...'
    }
    $stagingRoot = Join-Path $installRoot '.setup'
    $staging = Join-Path $stagingRoot ([guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    $archive = Join-Path $staging 'LeadFinder.zip'
    Write-Host '[1/5] Downloading LeadFinder...'
    $sourceRef = if ($env:LEADFINDER_SOURCE_REF) { $env:LEADFINDER_SOURCE_REF } else { 'refs/heads/FinalFinal' }
    if ($sourceRef -notmatch '^[a-zA-Z0-9/_-]+$') { throw 'The application version reference is invalid.' }
    Invoke-WebRequest -UseBasicParsing -Uri "https://codeload.github.com/Nocccenttt/LeadFinderConnector/zip/$sourceRef" -OutFile $archive -TimeoutSec 300
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $staging 'source')
    $source = @(Get-ChildItem -LiteralPath (Join-Path $staging 'source') -Directory)
    if ($source.Count -ne 1 -or !(Test-Path (Join-Path $source[0].FullName 'scripts\Install-LeadFinder.ps1'))) { throw 'The downloaded application package is incomplete.' }
    # The installer checks active work before replacing any installed files.
    $options = @{ SourceRoot=$source[0].FullName; ConfigSource=(Join-Path (Split-Path -Parent $env:LEADFINDER_SETUP_FILE) '.env') }
    if ($env:LEADFINDER_NO_LAUNCH -eq '1') { $options.NoLaunch = $true }
    if ($env:LEADFINDER_SKIP_KEY_PROMPT -eq '1') { $options.SkipKeyPrompt = $true }
    if ($env:LEADFINDER_SHORTCUT_FOLDER) { $options.ShortcutFolder = $env:LEADFINDER_SHORTCUT_FOLDER }
    & (Join-Path $source[0].FullName 'scripts\Install-LeadFinder.ps1') @options
    if ($LASTEXITCODE -ne 0) { throw 'Application setup failed.' }
} catch {
    Write-Host "Setup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($staging -and (Test-Path -LiteralPath $staging)) {
        $resolved = [IO.Path]::GetFullPath($staging)
        $expectedParent = [IO.Path]::GetFullPath((Join-Path $installRoot '.setup'))
        if ([IO.Path]::GetDirectoryName($resolved) -eq $expectedParent -and [IO.Path]::GetFileName($resolved) -match '^[a-f0-9]{32}$') {
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
}
