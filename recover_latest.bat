@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo.
echo Recovering meeting from 10:03 PM - 10:13 PM (Feb 5, 2026)
echo This will take several minutes...
echo.
python -c "from recover_meeting import recover_meeting; recover_meeting('20260205_220300', '20260205_221400')"
if errorlevel 1 (
    echo.
    echo Recovery encountered an error - see above
)
echo.
echo Done! Check Downloads folder for summary.
pause
