[CmdletBinding()]
param(
  [switch]$FeatureWorktree,
  [string]$DesktopPath
)

$ErrorActionPreference = "Stop"
$installRoot = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
$isTemporaryWorktree = $installRoot -match "[\\/]\.worktrees[\\/]"
if ($isTemporaryWorktree -and -not $FeatureWorktree) {
  throw "This path is a feature worktree. Use -FeatureWorktree for an explicit RC shortcut."
}

$desktop = if ([string]::IsNullOrWhiteSpace($DesktopPath)) {
  [Environment]::GetFolderPath("Desktop")
} else {
  (Resolve-Path $DesktopPath).Path
}
if ([string]::IsNullOrWhiteSpace($desktop) -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
  throw "Desktop directory was not found: $desktop"
}

$launcherScript = Join-Path $installRoot "launcher\launch_agentforge.vbs"
if (-not (Test-Path -LiteralPath $launcherScript -PathType Leaf)) {
  throw "AgentForge launcher entry point was not found: $launcherScript"
}
$wscript = Join-Path $env:WINDIR "System32\wscript.exe"
if (-not (Test-Path -LiteralPath $wscript -PathType Leaf)) {
  throw "Windows Script Host was not found: $wscript"
}

$displaySuffix = ([char]0x4E00), ([char]0x952E), ([char]0x542F), ([char]0x52A8) -join ""
$productName = "AgentForge " + $displaySuffix
$shortcutName = if ($FeatureWorktree) { $productName + " (RC)" } else { $productName }
$shortcutPath = Join-Path $desktop ($shortcutName + ".lnk")
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $wscript
$shortcut.Arguments = '//nologo "' + $launcherScript + '"'
$shortcut.WorkingDirectory = $installRoot
$shortcut.Description = "Start the AgentForge operations console"
$shortcut.IconLocation = "$env:WINDIR\System32\shell32.dll,13"
$shortcut.WindowStyle = 1
$shortcut.Save()

[PSCustomObject]@{
  Name = $shortcutName
  Path = $shortcutPath
  Target = $wscript
  Arguments = $shortcut.Arguments
  WorkingDirectory = $installRoot
  Mode = if ($FeatureWorktree) { "feature-worktree" } else { "main" }
} | ConvertTo-Json -Compress
