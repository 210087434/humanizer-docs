$ErrorActionPreference = 'Stop'
$RootDir = Split-Path $PSScriptRoot -Parent
$ExePath = Join-Path $RootDir "HumanizeHelper.exe"
$StartupDir = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupDir "HumanizeHelper.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = $RootDir
$Shortcut.Description = "Humanize Helper — Word to Clever AI background bridge"
$Shortcut.Save()

Write-Output "Installed startup shortcut at: $ShortcutPath"
Write-Output "Target: $ExePath"
