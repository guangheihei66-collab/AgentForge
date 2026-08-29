@echo off
setlocal
wscript.exe //nologo "%~dp0launch_agentforge.vbs"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
