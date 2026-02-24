@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
python -c "from recover_meeting import recover_meeting; recover_meeting('20260205_203900', '20260205_212300')"
if errorlevel 1 (
    echo.
    echo Recovery failed - see error above
)
pause
