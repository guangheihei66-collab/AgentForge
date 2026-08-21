@echo off
setlocal
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\stop_agentforge.ps1"
pause
