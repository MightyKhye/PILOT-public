@echo off
echo Installing Quick Recorder dependencies...
cd /d "%~dp0"
pip install -r requirements.txt
echo.
echo Installation complete!
echo.
echo To run: Double-click launch_recorder.bat
echo Or run: python recorder.py
echo.
pause
