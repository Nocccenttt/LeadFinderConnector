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
    echo Python is not installed.
    echo.
    echo Please install Python 3.11 or newer from:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo Python found.
python --version
echo.

REM --------------------------------------------
REM Check .env
REM --------------------------------------------
if not exist ".env" (
    echo ERROR: .env file was not found.
    echo.
    echo Put your .env file in this folder:
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
    python -m venv .venv

    if errorlevel 1 (
        echo.
        echo ERROR: Could not create virtual environment.
        pause
        exit /b 1
    )
)

echo Virtual environment ready.
echo.

REM --------------------------------------------
REM Upgrade pip
REM --------------------------------------------
echo Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

REM --------------------------------------------
REM Install required packages
REM --------------------------------------------
echo.
echo Installing LeadFinder dependencies...
echo.

".venv\Scripts\python.exe" -m pip install Flask openai python-dotenv beautifulsoup4 requests

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