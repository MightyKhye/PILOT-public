"""Create a desktop shortcut for REMShadow."""

import os
import sys
from pathlib import Path

def create_shortcut():
    """Create desktop shortcut for REMShadow."""

    # Get paths
    assistant_dir = Path(__file__).parent
    python_exe = assistant_dir / "venv" / "Scripts" / "pythonw.exe"  # Use pythonw to run without console
    main_script = assistant_dir / "src" / "main.py"
    desktop = Path.home() / "Desktop"

    # Icon path (use Python icon if no custom icon)
    icon_path = assistant_dir / "remshadow_icon.ico"
    if not icon_path.exists():
        icon_path = python_exe  # Use Python exe icon as fallback

    # Create .bat file that launches REMShadow
    bat_path = assistant_dir / "launch_remshadow.bat"
    bat_content = f'''@echo off
cd /d "{assistant_dir}"
start "" "{python_exe}" -m src.main
'''

    with open(bat_path, 'w') as f:
        f.write(bat_content)

    print(f"Created launcher: {bat_path}")

    # Create VBS script to create the shortcut
    vbs_path = assistant_dir / "create_shortcut.vbs"
    shortcut_path = desktop / "REMShadow.lnk"

    vbs_content = f'''Set oWS = WScript.CreateObject("WScript.Shell")
Set oLink = oWS.CreateShortcut("{shortcut_path}")
oLink.TargetPath = "{bat_path}"
oLink.WorkingDirectory = "{assistant_dir}"
oLink.Description = "REMShadow - Meeting Transcription & Analysis"
oLink.IconLocation = "{icon_path}"
oLink.Save
'''

    with open(vbs_path, 'w') as f:
        f.write(vbs_content)

    # Run the VBS script to create shortcut
    import subprocess
    result = subprocess.run(['cscript.exe', '//NoLogo', str(vbs_path)],
                          capture_output=True, text=True)

    if result.returncode == 0:
        print(f"\nDesktop shortcut created: {shortcut_path}")
        print("\nYou can now:")
        print("  1. Double-click 'REMShadow' on your desktop to launch")
        print("  2. Right-click the tray icon → 'Upload Meeting Recording' to process audio files")
        print("  3. Right-click the tray icon → 'Start Recording' for live meetings")
    else:
        print(f"\nError creating shortcut: {result.stderr}")

    # Cleanup VBS script
    vbs_path.unlink()

if __name__ == '__main__':
    try:
        create_shortcut()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    input("\nPress Enter to exit...")
