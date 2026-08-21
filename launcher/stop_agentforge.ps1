$ErrorActionPreference = "SilentlyContinue"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dataRoot = if ($env:AGENTFORGE_DATA_ROOT) { $env:AGENTFORGE_DATA_ROOT } else { "D:\AgentProjectData\AgentForge" }
$runtime = Join-Path $dataRoot "runtime"
$logs = Join-Path $runtime "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Write-LauncherLog([string]$message) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
  Add-Content -LiteralPath (Join-Path $logs "launcher.log") -Value $line
  Write-Host $line
}

function Get-CommandLine([int]$processId) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
  if ($process) { return [string]$process.CommandLine }
  return ""
}

function Test-DescendantCommand([int]$processId, [string]$needle) {
  $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $processId }
  foreach ($child in $children) {
    $childCommand = ([string]$child.CommandLine).ToLowerInvariant()
    if ($childCommand.Contains($needle.ToLowerInvariant())) { return $true }
    if (Test-DescendantCommand ([int]$child.ProcessId) $needle) { return $true }
  }
  return $false
}

function Stop-Tree([int]$processId) {
  $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $processId }
  foreach ($child in $children) { Stop-Tree ([int]$child.ProcessId) }
  Stop-Process -Id $processId -Force
}

function Stop-OwnedProcess([string]$name, [string]$kind) {
  $path = Join-Path $runtime $name
  if (-not (Test-Path -LiteralPath $path)) { return }
  $processId = [int](Get-Content -LiteralPath $path -Raw).Trim()
  $commandLine = (Get-CommandLine $processId).ToLowerInvariant()
  $isOwned = $false
  if ($kind -eq "backend") {
    $isOwned = $commandLine.Contains("uvicorn app.main:app") -and ($commandLine.Contains($root.ToLowerInvariant()) -or $commandLine.Contains("agentforge"))
  } else {
    $isOwned = $commandLine.Contains("run dev") -and ($commandLine.Contains((Join-Path $root "frontend").ToLowerInvariant()) -or (Test-DescendantCommand $processId (Join-Path $root "frontend")))
  }
  if ($isOwned -and (Get-Process -Id $processId)) {
    Stop-Tree $processId
    Write-LauncherLog "Stopped owned $kind process tree rooted at $processId"
  } elseif (Get-Process -Id $processId) {
    Write-LauncherLog "Skipped PID $processId because its command line is not an AgentForge $kind process"
  } else {
    Write-LauncherLog "PID $processId is no longer running"
  }
  Remove-Item -LiteralPath $path -Force
}

Stop-OwnedProcess "launcher-backend.pid" "backend"
Stop-OwnedProcess "launcher-frontend.pid" "frontend"
Write-LauncherLog "AgentForge launcher stop complete. Unrelated processes were not touched."
