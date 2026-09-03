# WebChat2Local Server PowerShell Launcher
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "WebChat2Local Gateway"

Set-Location -LiteralPath $PSScriptRoot
$pythonExe = "C:\Users\Administrator\venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) { $pythonExe = "python" }

Write-Host "[WebChat2Local] Starting local Gemini Web bridge..." -ForegroundColor Cyan
Write-Host "[WebChat2Local] Workspace: $PSScriptRoot" -ForegroundColor DarkGray
Write-Host "[WebChat2Local] Python: $pythonExe" -ForegroundColor DarkGray
Write-Host "[WebChat2Local] URL: http://127.0.0.1:8765/" -ForegroundColor DarkGray
& $pythonExe desktop_app.py
