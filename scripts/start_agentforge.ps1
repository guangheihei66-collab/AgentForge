$ErrorActionPreference = "Stop"
$entry = Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "launcher\launch_agentforge.vbs"
$wscript = Join-Path $env:WINDIR "System32\wscript.exe"
if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) { throw "Launcher entry point not found: $entry" }
if (-not (Test-Path -LiteralPath $wscript -PathType Leaf)) { throw "Windows Script Host not found: $wscript" }
Start-Process -FilePath $wscript -ArgumentList "//nologo `"$entry`"" -WindowStyle Hidden
