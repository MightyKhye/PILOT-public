@echo off
REM Create Desktop Shortcut for Meeting Listener

echo Creating desktop shortcut...

REM Create VBS script to make shortcut
set SCRIPT="%TEMP%\create_shortcut.vbs"
set DESKTOP=%USERPROFILE%\Desktop
set TARGET=%~dp0launch_meeting_listener.bat
set SHORTCUT=%DESKTOP%\Pilot Meeting Assistant.lnk

echo Set oWS = WScript.CreateObject("WScript.Shell") > %SCRIPT%
echo sLinkFile = "%SHORTCUT%" >> %SCRIPT%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%
echo oLink.TargetPath = "%TARGET%" >> %SCRIPT%
echo oLink.WorkingDirectory = "%~dp0" >> %SCRIPT%
echo oLink.Description = "Pilot — AI Meeting Assistant: Record, Transcribe, Analyze" >> %SCRIPT%
echo oLink.IconLocation = "%SystemRoot%\System32\shell32.dll,13" >> %SCRIPT%
echo oLink.Save >> %SCRIPT%

REM Execute VBS script
cscript /nologo %SCRIPT%
del %SCRIPT%

echo.
echo Desktop shortcut created successfully!
echo Look for "Pilot Meeting Assistant" on your desktop.
echo.
pause
