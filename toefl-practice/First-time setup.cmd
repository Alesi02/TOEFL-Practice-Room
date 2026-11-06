@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0First-time setup.ps1"
set "taskSetupExit=%errorlevel%"
pause
exit /b %taskSetupExit%
