param(
  [switch]$ResolvePythonOnly,
  [switch]$ResolveConfigOnly,
  [string]$LocalConfigPath
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$defaultLocalConfigPath = Join-Path $PSScriptRoot ".env.local"
$effectiveLocalConfigPath = if ([string]::IsNullOrWhiteSpace($LocalConfigPath)) {
  $defaultLocalConfigPath
} else {
  $LocalConfigPath
}

function Import-LocalDeveloperConfig([string]$path) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return }
  $allowed = @(
    "AGENTFORGE_PYTHON",
    "AGENTFORGE_LLM_PROVIDER",
    "AGENTFORGE_LLM_BASE_URL",
    "AGENTFORGE_LLM_MODEL",
    "AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE"
  )
  foreach ($line in Get-Content -LiteralPath $path) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#") -or $trimmed.StartsWith(";")) { continue }
    $separator = $trimmed.IndexOf("=")
    if ($separator -le 0) { continue }
    $name = $trimmed.Substring(0, $separator).Trim()
    if ($allowed -notcontains $name) { continue }
    if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, "Process"))) { continue }
    $value = $trimmed.Substring($separator + 1).Trim()
    if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
  }
}

Import-LocalDeveloperConfig $effectiveLocalConfigPath
$dataRoot = if ($env:AGENTFORGE_DATA_ROOT) { $env:AGENTFORGE_DATA_ROOT } else { "D:\AgentProjectData\AgentForge" }
$runtime = Join-Path $dataRoot "runtime"
$logs = Join-Path $runtime "logs"
$backendLog = Join-Path $logs "backend.log"
$backendErrorLog = Join-Path $logs "backend-error.log"
$bootstrapLog = Join-Path $logs "launcher-bootstrap.log"
$frontendLog = Join-Path $logs "frontend.log"
$frontendErrorLog = Join-Path $logs "frontend-error.log"
$backendPidFile = Join-Path $runtime "launcher-backend.pid"
$frontendPidFile = Join-Path $runtime "launcher-frontend.pid"

New-Item -ItemType Directory -Force -Path $runtime, $logs | Out-Null

function Write-LauncherLog([string]$message) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
  Add-Content -LiteralPath (Join-Path $logs "launcher.log") -Value $line
  Write-Host $line
}

function Fail([string]$message) {
  Write-LauncherLog "ERROR: $message"
  throw $message
}

function Get-ProcessCommandLine([int]$processId) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
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

function Test-ExpectedProcess([int]$processId, [string]$kind) {
  $commandLine = Get-ProcessCommandLine $processId
  if (-not $commandLine) { return $false }
  $normalized = $commandLine.ToLowerInvariant()
  $rootMatch = $root.ToLowerInvariant()
  if ($kind -eq "backend") {
    return $normalized.Contains("uvicorn app.main:app") -and ($normalized.Contains($rootMatch) -or $normalized.Contains("agentforge"))
  }
  return $normalized.Contains("run dev") -and ($normalized.Contains((Join-Path $root "frontend").ToLowerInvariant()) -or (Test-DescendantCommand $processId (Join-Path $root "frontend")))
}

function Test-HttpHealth {
  try {
    return (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8000/health" -TimeoutSec 2).StatusCode -eq 200
  } catch { return $false }
}

function Test-Port([int]$port) {
  try {
    $connection = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $port -State Listen -ErrorAction Stop
    return $null -ne $connection
  } catch { return $false }
}

function Wait-Until([scriptblock]$condition, [int]$timeoutSeconds, [string]$description) {
  $deadline = (Get-Date).AddSeconds($timeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (& $condition) { Write-LauncherLog (("{0}: ready" -f $description)); return }
    Start-Sleep -Milliseconds 500
  }
  Fail "$description did not become ready within $timeoutSeconds seconds. See $logs."
}

$pythonOverride = $env:AGENTFORGE_PYTHON
$hasPythonOverride = -not [string]::IsNullOrWhiteSpace($pythonOverride)
$python = if ($hasPythonOverride) {
  $pythonOverride
} else {
  Join-Path $root "backend\.venv\Scripts\python.exe"
}

if ($ResolveConfigOnly) {
  [PSCustomObject]@{
    AGENTFORGE_PYTHON = $python
    AGENTFORGE_LLM_PROVIDER = $env:AGENTFORGE_LLM_PROVIDER
    AGENTFORGE_LLM_BASE_URL = $env:AGENTFORGE_LLM_BASE_URL
    AGENTFORGE_LLM_MODEL = $env:AGENTFORGE_LLM_MODEL
    AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE = $env:AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE
  } | ConvertTo-Json -Compress
  exit 0
}

if ($ResolvePythonOnly) {
  if ($hasPythonOverride -and -not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Configured AGENTFORGE_PYTHON does not exist: $python"
  }
  Write-Output $python
  exit 0
}

try {
  Write-LauncherLog "Starting AgentForge from $root"
  if ($hasPythonOverride) {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { Fail "Configured AGENTFORGE_PYTHON does not exist: $python" }
  } elseif (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Fail "Backend virtual environment not found: $python"
  }
  $node = Get-Command node.exe -ErrorAction SilentlyContinue
  $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
  if (-not $node) { Fail "Node.js was not found on PATH." }
  if (-not $npm) { Fail "npm.cmd was not found on PATH." }
  Write-LauncherLog "Python environment: $(& $python --version 2>&1)"
  Write-LauncherLog "Node environment: $(& $node.Source --version 2>&1); npm $(& $npm.Source --version 2>&1)"

  $env:PYTHONPATH = Join-Path $root "backend"
  & $python -c "from app.storage.database import init_db; init_db()" *>> $bootstrapLog
  if ($LASTEXITCODE -ne 0) { Fail "Database initialization failed." }
  & $python (Join-Path $root "scripts\seed_demo.py") *>> $bootstrapLog
  if ($LASTEXITCODE -ne 0) { Fail "Demo data initialization failed." }

  if (Test-Path -LiteralPath $backendPidFile) {
    $existingBackendPid = [int](Get-Content -LiteralPath $backendPidFile -Raw).Trim()
    if (-not (Get-Process -Id $existingBackendPid -ErrorAction SilentlyContinue) -or -not (Test-ExpectedProcess $existingBackendPid "backend")) {
      Remove-Item -LiteralPath $backendPidFile -Force -ErrorAction SilentlyContinue
    }
  }

  if (-not (Test-HttpHealth)) {
    if (Test-Port 8000) { Fail "Port 8000 is occupied, but the service is not a healthy AgentForge backend." }
    $backend = Start-Process -FilePath $python -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory (Join-Path $root "backend") -RedirectStandardOutput $backendLog -RedirectStandardError $backendErrorLog -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $backendPidFile -Value $backend.Id
    Write-LauncherLog "Started backend process $($backend.Id)"
  } else {
    Write-LauncherLog "Healthy backend already running; no duplicate process started."
  }
  Wait-Until { Test-HttpHealth } 30 "Backend health check"

  if (Test-Path -LiteralPath $frontendPidFile) {
    $existingFrontendPid = [int](Get-Content -LiteralPath $frontendPidFile -Raw).Trim()
    if (-not (Get-Process -Id $existingFrontendPid -ErrorAction SilentlyContinue) -or -not (Test-ExpectedProcess $existingFrontendPid "frontend")) {
      Remove-Item -LiteralPath $frontendPidFile -Force -ErrorAction SilentlyContinue
    }
  }

  if (-not (Test-Port 5173)) {
    $frontend = Start-Process -FilePath $npm.Source -ArgumentList "run dev -- --host 127.0.0.1" -WorkingDirectory (Join-Path $root "frontend") -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrorLog -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $frontendPidFile -Value $frontend.Id
    Write-LauncherLog "Started frontend process $($frontend.Id)"
  } else {
    Write-LauncherLog "Port 5173 is already available; no duplicate frontend process started."
  }
  Wait-Until { Test-Port 5173 } 30 "Frontend port check"

  Start-Process "http://localhost:5173"
  Write-LauncherLog "AgentForge is ready: http://localhost:5173"
} catch {
  Write-Host "AgentForge startup failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Runtime logs: $logs" -ForegroundColor Yellow
  exit 1
}
