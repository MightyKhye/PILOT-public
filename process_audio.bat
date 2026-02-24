@echo off
echo.
echo REMShadow Audio File Processor
echo ================================
echo.
echo Drag and drop an audio file onto this window, then press Enter.
echo Supported formats: WAV, M4A (iPhone voice memos), MP3
echo.
set /p audiofile="Audio file path: "

if "%audiofile%"=="" (
    echo Error: No file specified
    pause
    exit /b 1
)

echo.
echo Processing audio file...
echo.

venv\Scripts\python.exe process_audio_file.py %audiofile%

echo.
pause
