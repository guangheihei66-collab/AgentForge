$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dataRoot = if ($env:AGENTFORGE_DATA_ROOT) { $env:AGENTFORGE_DATA_ROOT } else { "D:\AgentProjectData\AgentForge" }
$runtime = Join-Path $dataRoot "runtime"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

$python = Join-Path $root "backend\.venv\Scripts\python.exe"
$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not (Test-Path $python)) { throw "Backend virtual environment not found: $python" }
if (-not $npm) { throw "Node/npm was not found on PATH." }

function Test-Running([int]$port) {
  try { return (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/health" -TimeoutSec 1).StatusCode -eq 200 } catch { return $false }
}

$env:PYTHONPATH = Join-Path $root "backend"
& $python -c "from app.storage.database import init_db; init_db()"
& $python (Join-Path $root "scripts\seed_demo.py")

$backendPidFile = Join-Path $runtime "backend.pid"
$frontendPidFile = Join-Path $runtime "frontend.pid"
if (-not (Test-Running 8000)) {
  $backend = Start-Process -FilePath $python -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory (Join-Path $root "backend") -RedirectStandardOutput (Join-Path $runtime "backend.log") -RedirectStandardError (Join-Path $runtime "backend-error.log") -WindowStyle Hidden -PassThru
  Set-Content -LiteralPath $backendPidFile -Value $backend.Id
}
if (-not (Test-Path $frontendPidFile)) {
  $frontend = Start-Process -FilePath $npm -ArgumentList "run dev -- --host 127.0.0.1" -WorkingDirectory (Join-Path $root "frontend") -RedirectStandardOutput (Join-Path $runtime "frontend.log") -RedirectStandardError (Join-Path $runtime "frontend-error.log") -WindowStyle Hidden -PassThru
  Set-Content -LiteralPath $frontendPidFile -Value $frontend.Id
}

Start-Process "http://localhost:5173"
Write-Host "AgentForge started: http://localhost:5173"
