@echo off
cd /d "%~dp0"
echo [DevMode] Starting ProxiTalk in dev mode...
echo [DevMode] App changes will hot-reload the affected app.
echo [DevMode] Core OS changes will restart the whole process.
echo.
.venv\Scripts\python.exe core_os\entry_emulator_windows.py --dev
