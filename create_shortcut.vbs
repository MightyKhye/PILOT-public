Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "C:\Users\khyeh\Desktop\Pilot.lnk"
Set oLink = oWS.CreateShortcut(sLinkFile)
    oLink.TargetPath = "C:\Users\khyeh\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
    oLink.Arguments = "C:\Users\khyeh\assistant\src\main.py"
    oLink.WorkingDirectory = "C:\Users\khyeh\assistant\src"
    oLink.IconLocation = "C:\Users\khyeh\assistant\pilot_brain_v3.ico,0"
    oLink.Description = "Pilot - Meeting Assistant"
oLink.Save
WScript.Echo "Shortcut created with correct Python path!"
