@echo off
setlocal
cd /d "%~dp0"

title LeadFinder
color 0B

echo ============================================
echo             LEADFINDER
echo ============================================
echo.

REM --------------------------------------------
REM Check Python
REM --------------------------------------------
where python >nul 2>&1

if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 (
        echo Python is not installed.
        echo.
        echo Please install Python 3.11 or newer from:
        echo https://www.python.org/downloads/
        echo.
        pause
        exit /b 1
    )
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)

echo Python found.
%PYTHON% --version
%PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
    echo.
    echo ERROR: LeadFinder requires Python 3.11 or newer.
    pause
    exit /b 1
)
echo.

REM --------------------------------------------
REM Check .env
REM --------------------------------------------
if not exist ".env" (
    echo ERROR: .env file was not found.
    echo.
    echo Copy .env.example to .env and enter your API keys.
    echo Keep .env private; it is excluded from Git.
    echo.
    echo Project folder:
    echo %CD%
    echo.
    pause
    exit /b 1
)

echo .env found.
echo.

REM --------------------------------------------
REM Create virtual environment
REM --------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON% -m venv .venv

    if errorlevel 1 (
        echo.
        echo ERROR: Could not create virtual environment.
        pause
        exit /b 1
    )
)

echo Virtual environment ready.
echo.

".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
    echo ERROR: The existing .venv uses Python older than 3.11.
    echo Delete the .venv folder and run this launcher again.
    pause
    exit /b 1
)

REM --------------------------------------------
REM Install required packages
REM --------------------------------------------
echo.
echo Installing LeadFinder dependencies...
echo.

".venv\Scripts\python.exe" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Dependency installation failed.
    echo.
    pause
    exit /b 1
)

echo.
echo Dependencies ready.
echo.

REM --------------------------------------------
REM Start browser
REM --------------------------------------------
echo Starting LeadFinder dashboard...
echo.
echo Dashboard:
echo http://127.0.0.1:3000
echo.
echo Keep this window open while using LeadFinder.
echo Press CTRL+C here to stop LeadFinder.
echo.

timeout /t 3 /nobreak >nul

start "" "http://127.0.0.1:3000"

REM --------------------------------------------
REM Start Flask
REM --------------------------------------------
".venv\Scripts\python.exe" preview_dashboard.py

echo.
echo ============================================
echo LeadFinder has stopped.
echo ============================================
pause
