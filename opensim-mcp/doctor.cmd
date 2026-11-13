@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\doctor.ps1" %*
if errorlevel 1 (echo Environment needs attention. & pause & exit /b 1)
pause
