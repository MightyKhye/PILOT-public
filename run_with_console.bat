@echo off
echo ============================================================
echo           MEETING LISTENER - System Tray App
echo ============================================================
echo.
echo The app is now running in the system tray!
echo.
echo Look for the MICROPHONE ICON in your system tray:
echo   - Bottom-right corner of taskbar
echo   - May be in the overflow area (click ^ arrow)
echo.
echo Right-click the icon to:
echo   - Start Recording
echo   - Stop Recording
echo   - View Status
echo   - Exit
echo.
echo This window will stay open while the app runs.
echo Close this window to stop the app.
echo ============================================================
echo.

REM Activate virtual environment and run
call venv\Scripts\activate.bat
python -m src.main

pause
