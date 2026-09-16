@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "logs" mkdir "logs"
if not exist "outputs" mkdir "outputs"
if not exist "codex_handoffs" mkdir "codex_handoffs"

for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set TODAY=%%c-%%a-%%b
set "LOG=logs\LeadFinder_%TODAY%.log"

echo ================================================== >> "%LOG%"
echo LeadFinder started: %date% %time% >> "%LOG%"
echo Folder: %CD% >> "%LOG%"
echo ================================================== >> "%LOG%"

if not exist "seo_lead_finder_prospecting_batch.py" (
  echo ERROR: Python script not found. >> "%LOG%"
  echo ERROR: seo_lead_finder_prospecting_batch.py not found.
  pause
  exit /b 1
)

if "%GOOGLE_MAPS_API_KEY%"=="" (
  echo ERROR: GOOGLE_MAPS_API_KEY is not set. >> "%LOG%"
  echo ERROR: GOOGLE_MAPS_API_KEY is not set.
  echo Set the environment variable, then open a new Command Prompt/PowerShell.
  pause
  exit /b 1
)

set /p "NICHE=Enter niche (example: plumber): "
set /p "AREA=Enter area (example: Philadelphia, PA): "
set /p "MAX=Max leads [20]: "
if "%MAX%"=="" set "MAX=20"

echo Niche: %NICHE% >> "%LOG%"
echo Area: %AREA% >> "%LOG%"
echo Max leads: %MAX% >> "%LOG%"
echo. >> "%LOG%"

echo.
echo Searching...
echo Progress will appear below as each stage completes.
echo.

python -u "seo_lead_finder_prospecting_batch.py" --niche "%NICHE%" --area "%AREA%" --max-results "%MAX%" --output-dir "outputs" >> "%LOG%" 2>&1
set "EXITCODE=%ERRORLEVEL%"

echo. >> "%LOG%"
echo Finished: %date% %time% >> "%LOG%"
echo Exit code: %EXITCODE% >> "%LOG%"

echo.
if "%EXITCODE%"=="0" (
  echo DONE.
  echo.
  echo All leads:       outputs\
  echo HIGH leads:      codex_handoffs\HIGH\
  echo MEDIUM leads:    codex_handoffs\MEDIUM\
  echo LOW leads:       codex_handoffs\LOW\
  echo Priority folders: codex_handoffs\
  echo Logs:            logs\
) else (
  echo LeadFinder finished with an error. Check:
  echo %LOG%
)

echo.
pause
exit /b %EXITCODE%
