# WebChat2Local Server PowerShell Launcher
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "WebChat2Local Gateway"

Set-Location -LiteralPath $PSScriptRoot
$pythonExe = "C:\Users\Administrator\venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) { $pythonExe = "python" }

Write-Host "[WebChat2Local] 正在啟動伺服器與系統匣背景常駐..." -ForegroundColor Cyan
& $pythonExe desktop_app.py
