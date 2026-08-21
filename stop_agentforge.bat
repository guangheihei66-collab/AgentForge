@echo off
setlocal
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_agentforge.ps1"
pause
