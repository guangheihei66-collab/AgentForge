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
$python = if ($env:AGENTFORGE_PYTHON) {
  $env:AGENTFORGE_PYTHON
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
  if ($env:AGENTFORGE_PYTHON -and -not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Configured AGENTFORGE_PYTHON does not exist: $python"
  }
  Write-Output $python
  exit 0
}

# Normal user-facing startup is delegated to Windows Script Host. The VBS
# entry resolves pythonw.exe and the Python controller owns the service Job
# Object, single-instance boundary, tray, health checks, and external logs.
$entry = Join-Path $PSScriptRoot "launch_agentforge.vbs"
$wscript = Join-Path $env:WINDIR "System32\wscript.exe"
if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) { throw "Launcher entry point not found: $entry" }
if (-not (Test-Path -LiteralPath $wscript -PathType Leaf)) { throw "Windows Script Host not found: $wscript" }
Start-Process -FilePath $wscript -ArgumentList ('//nologo "' + $entry + '"') -WindowStyle Hidden
exit 0
