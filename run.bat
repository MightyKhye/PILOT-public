@echo off
REM Meeting Listener - Quick Start Script

echo Starting Meeting Listener...
echo.

REM Activate virtual environment
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo Error: Virtual environment not found!
    echo Please run: python -m venv venv
    echo Then: venv\Scripts\activate
    echo Then: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Run the application
python -m src.main

REM Deactivate on exit
deactivate
