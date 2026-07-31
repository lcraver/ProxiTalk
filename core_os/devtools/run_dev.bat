@echo off
if "%~1"=="--relaunched" goto :start

powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process -FilePath '%~f0' -ArgumentList '--relaunched' -WindowStyle Hidden"
exit /b

:start
cd /d "%~dp0\..\.."
.venv\Scripts\python.exe core_os\entry_emulator_windows.py --dev
