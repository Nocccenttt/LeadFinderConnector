@echo off
setlocal

cd /d "%~dp0"

title LeadFinder

echo.
echo ========================================
echo              LEADFINDER
echo ========================================
echo.

REM ========================================
REM CHECK PYTHON
REM ========================================

where python >nul 2>&1

if errorlevel 1 (
    echo ERROR: Python is not installed.
    echo.
    echo Please install Python 3.11 or newer.
    echo.
    pause
    exit /b 1
)

echo [OK] Python detected.

REM ========================================
REM CHECK .ENV
REM ========================================

if not exist ".env" (
    echo.
    echo ERROR: .env file was not found.
    echo.
    echo Please place your .env file in:
    echo %CD%
    echo.
    pause
    exit /b 1
)

echo [OK] .env detected.

REM ========================================
REM CREATE VIRTUAL ENVIRONMENT
REM ========================================

if not exist ".venv\Scripts\python.exe" (

    echo.
    echo Creating Python environment...
    echo.

    python -m venv .venv

    if errorlevel 1 (
        echo.
        echo ERROR: Could not create Python environment.
        echo.
        pause
        exit /b 1
    )
)

echo [OK] Python environment ready.

REM ========================================
REM INSTALL REQUIRED PACKAGES
REM ========================================

echo.
echo Installing/checking dependencies...
echo.

".venv\Scripts\python.exe" -m pip install --upgrade pip

".venv\Scripts\python.exe" -m pip install Flask openai python-dotenv beautifulsoup4 requests

if errorlevel 1 (
    echo.
    echo ERROR: Could not install required packages.
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Dependencies installed.

REM ========================================
REM START LEADFINDER
REM ========================================

echo.
echo ========================================
echo        STARTING LEADFINDER
echo ========================================
echo.

echo Dashboard:
echo http://127.0.0.1:3000
echo.

timeout /t 2 /nobreak >nul

start "" http://127.0.0.1:3000

".venv\Scripts\python.exe" preview_dashboard.py

echo.
echo ========================================
echo       LEADFINDER HAS STOPPED
echo ========================================
echo.

pause