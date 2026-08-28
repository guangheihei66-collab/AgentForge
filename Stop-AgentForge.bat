@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
wscript.exe //nologo "%PROJECT_ROOT%launcher\control_agentforge.vbs" exit
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
