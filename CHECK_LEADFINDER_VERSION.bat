@echo off
cd /d "%~dp0"
echo.
echo LeadFinder folder:
echo %CD%
echo.
echo Python script being used:
where python
echo.
echo Checking LeadFinder arguments:
python "seo_lead_finder_prospecting_batch.py" --help
echo.
pause
