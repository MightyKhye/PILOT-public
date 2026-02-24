@echo off
REM Pilot — AI Meeting Assistant
REM Activates venv, auto-adds ffmpeg to PATH, then starts the app.

title Pilot Meeting Assistant

REM Change to this script's directory
cd /d "%~dp0"

REM Activate virtual environment
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo Error: Virtual environment not found.
    echo Run setup first:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

REM Add common ffmpeg install locations to PATH (safe no-ops if dirs don't exist)
if exist "C:\ProgramData\chocolatey\bin\ffmpeg.exe"       set "PATH=C:\ProgramData\chocolatey\bin;%PATH%"
if exist "C:\ffmpeg\bin\ffmpeg.exe"                       set "PATH=C:\ffmpeg\bin;%PATH%"
if exist "C:\Program Files\ffmpeg\bin\ffmpeg.exe"         set "PATH=C:\Program Files\ffmpeg\bin;%PATH%"
if exist "C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe"   set "PATH=C:\Program Files (x86)\ffmpeg\bin;%PATH%"
if exist "C:\tools\ffmpeg\bin\ffmpeg.exe"                 set "PATH=C:\tools\ffmpeg\bin;%PATH%"
if exist "%USERPROFILE%\ffmpeg\bin\ffmpeg.exe"            set "PATH=%USERPROFILE%\ffmpeg\bin;%PATH%"

REM Launch the system tray application
python -m src.main

REM Keep window visible if the app crashes
if errorlevel 1 (
    echo.
    echo Pilot exited with an error. Check logs\ for details.
    pause >nul
)

deactivate
