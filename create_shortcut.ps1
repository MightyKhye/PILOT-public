$WScriptShell = New-Object -ComObject WScript.Shell
$Desktop = [System.Environment]::GetFolderPath('Desktop')

# Remove old shortcut if it exists
$OldShortcut = "$Desktop\NEXPLANON REMS Meeting Listener.lnk"
if (Test-Path $OldShortcut) {
    Remove-Item $OldShortcut -Force
    Write-Host "Removed old shortcut"
}

# Create new shortcut with updated name and icon
$Shortcut = $WScriptShell.CreateShortcut("$Desktop\REMS Assistant.lnk")
$Shortcut.TargetPath = "C:\Users\khyeh\assistant\launch_meeting_listener.bat"
$Shortcut.WorkingDirectory = "C:\Users\khyeh\assistant"
$Shortcut.Description = "REMS Assistant - Meeting Listener, Transcription, and AI Analysis"
$Shortcut.IconLocation = "%SystemRoot%\System32\shell32.dll,71"
$Shortcut.Save()

Write-Host "Desktop shortcut created successfully!"
Write-Host "Look for 'REMS Assistant' on your desktop."
