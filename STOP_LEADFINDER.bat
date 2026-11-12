@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\Stop-LeadFinder.ps1"
exit /b %errorlevel%
