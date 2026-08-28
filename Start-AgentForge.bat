@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
wscript.exe //nologo "%PROJECT_ROOT%launcher\launch_agentforge.vbs"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
