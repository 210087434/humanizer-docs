$ErrorActionPreference = 'SilentlyContinue'
$StartupDir = [Environment]::GetFolderPath('Startup')
$ShortcutPath = Join-Path $StartupDir "HumanizeHelper.lnk"

if (Test-Path $ShortcutPath) {
    Remove-Item $ShortcutPath -Force
    Write-Output "Removed startup shortcut: $ShortcutPath"
}

Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -like '*desktop_app*app.py*' } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
    Write-Output "Stopped running Humanize Helper process (PID $($_.ProcessId))"
}

