@echo off
setlocal
wscript.exe //nologo "%~dp0control_agentforge.vbs" exit
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
