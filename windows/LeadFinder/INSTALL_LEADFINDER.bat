@echo off
setlocal
title Install LeadFinder
cd /d "%~dp0"
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0app\scripts\Install-LeadFinder.ps1" -SourceRoot "%~dp0app" -ConfigSource "%~dp0.env"
if errorlevel 1 (
    echo.
    echo Setup could not finish. The error is shown above. Run this file again to retry.
    pause
    exit /b 1
)
exit /b 0
