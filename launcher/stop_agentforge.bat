@echo off
setlocal
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_agentforge.ps1"
if errorlevel 1 pause
endlocal
