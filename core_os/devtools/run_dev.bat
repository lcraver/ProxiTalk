@echo off
cd /d "%~dp0\..\.."
echo [DevMode] Starting core_os (Windows emulator backend) in dev mode...
echo [DevMode] Any change under core_os\core, packages, apps_runtime,
echo [DevMode] apps\, bootstrap.py, or backends\emulator_windows restarts
echo [DevMode] the process. backends\device_pi is never watched here.
echo.
.venv\Scripts\python.exe core_os\entry_emulator_windows.py --dev
