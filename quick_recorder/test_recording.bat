@echo off
echo.
echo Quick Recorder Test
echo ===================
echo.
echo The recorder is now running.
echo Press Ctrl+Shift+R to start/stop recording
echo.
echo Keep this window open and try the hotkey!
echo.
cd /d "%~dp0"
python recorder.py
pause
