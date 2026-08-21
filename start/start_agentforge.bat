@echo off
setlocal
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\start_agentforge.ps1"
if errorlevel 1 pause
