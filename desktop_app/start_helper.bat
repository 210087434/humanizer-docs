@echo off
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -like '*desktop_app*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
start "" "C:\Program Files\IBM\SPSS Statistics\Python3\pythonw.exe" "%~dp0app.py"
