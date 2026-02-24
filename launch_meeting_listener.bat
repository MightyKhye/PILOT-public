@echo off
REM Pilot — AI Meeting Assistant
REM Launches the system tray application

title Pilot Meeting Assistant

REM Change to this script's directory
cd /d "%~dp0"

REM Activate virtual environment
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo Error: Virtual environment not found!
    echo Please run setup first: python -m venv venv
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

REM Keep window open on error
if errorlevel 1 (
    echo.
    echo An error occurred. Check logs\ for details.
    pause >nul
)

deactivate
