@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
call "%PROJECT_ROOT%launcher\start_agentforge.bat"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%
