@echo off
setlocal
PowerShell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_agentforge.ps1"
if errorlevel 1 (
  echo.
  echo AgentForge startup failed. Review the external runtime log path shown above.
  pause
  exit /b 1
)
endlocal
