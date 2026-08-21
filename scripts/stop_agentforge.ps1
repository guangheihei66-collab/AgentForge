$ErrorActionPreference = "SilentlyContinue"
$dataRoot = if ($env:AGENTFORGE_DATA_ROOT) { $env:AGENTFORGE_DATA_ROOT } else { "D:\AgentProjectData\AgentForge" }
$runtime = Join-Path $dataRoot "runtime"

function Stop-Tree([int]$processId) {
  $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $processId }
  foreach ($child in $children) { Stop-Tree ([int]$child.ProcessId) }
  Stop-Process -Id $processId -Force
}

foreach ($name in @("backend.pid", "frontend.pid")) {
  $path = Join-Path $runtime $name
  if (Test-Path $path) {
    $processId = [int](Get-Content -LiteralPath $path -Raw).Trim()
    if (Get-Process -Id $processId -ErrorAction SilentlyContinue) { Stop-Tree $processId }
    Remove-Item -LiteralPath $path -Force
  }
}
Write-Host "AgentForge processes stopped."
