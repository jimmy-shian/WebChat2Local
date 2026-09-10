@echo off
rem Launch the server with NO console window: pythonw runs desktop_app.py
rem (system-tray app) in the background. Close it from the tray icon menu.
wscript.exe "%~dp0start_server_hidden.vbs"
