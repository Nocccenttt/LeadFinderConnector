@echo off
setlocal
title Install LeadFinder
cd /d "%~dp0"
if exist "%~dp0scripts\Install-LeadFinder.ps1" (
    powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0scripts\Install-LeadFinder.ps1"
) else if exist "%~dp0app\scripts\Install-LeadFinder.ps1" (
    powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0app\scripts\Install-LeadFinder.ps1" -SourceRoot "%~dp0app" -ConfigSource "%~dp0.env"
) else (
    echo Setup files are missing. Extract the entire ZIP or restore the repository files, then try again.
    pause
    exit /b 1
)
set "LEADFINDER_SETUP_EXIT=%errorlevel%"
if not "%LEADFINDER_SETUP_EXIT%"=="0" (
    echo.
    echo Setup could not finish. The error is shown above. Run this file again to retry.
    pause
    exit /b %LEADFINDER_SETUP_EXIT%
)
exit /b 0
