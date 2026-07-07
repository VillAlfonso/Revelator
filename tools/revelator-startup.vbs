' ============================================================
'  Revelator auto-start (runs at Windows login)
'  Launches host-revelator.bat with NO console flash. The bat
'  itself opens the server + tunnel as two MINIMIZED windows
'  (sitting in the taskbar) so the site comes back on its own
'  every time you turn the laptop on and log in.
'
'  A copy of this file lives in the Startup folder. Delete that
'  copy to stop auto-hosting; this original stays here.
' ============================================================
Set sh = CreateObject("WScript.Shell")
' 0 = hidden window, False = don't wait for it to finish
sh.Run """C:\Revelator\host-revelator.bat""", 0, False
