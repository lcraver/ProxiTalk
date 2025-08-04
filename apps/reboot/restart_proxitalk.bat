@echo off
REM Windows batch script to restart ProxiTalk
REM Usage: restart_proxitalk.bat <python_exe> <script_path> <wait_seconds>

echo [Windows Restart] Starting restart script at %time%...
echo [Windows Restart] Python: %1
echo [Windows Restart] Script: %2
echo [Windows Restart] Wait time: %3 seconds

REM Write to log file
echo [Windows Restart] Started at %date% %time% > restart_log.txt
echo [Windows Restart] Args: %1 %2 %3 >> restart_log.txt

REM Wait for the specified time to allow cleanup
echo [Windows Restart] Waiting %3 seconds for cleanup...
echo [Windows Restart] About to wait >> restart_log.txt
timeout /t %3 /nobreak >nul

REM Start new ProxiTalk instance
echo [Windows Restart] Starting new ProxiTalk instance...
echo [Windows Restart] About to start ProxiTalk >> restart_log.txt
start "ProxiTalk" "%1" "%2"

if %errorlevel% equ 0 (
    echo [Windows Restart] New instance started successfully
    echo [Windows Restart] SUCCESS - Started successfully >> restart_log.txt
) else (
    echo [Windows Restart] Failed to start new instance, error code: %errorlevel%
    echo [Windows Restart] ERROR - Failed with code %errorlevel% >> restart_log.txt
)

echo [Windows Restart] Restart script complete at %time%
echo [Windows Restart] Complete at %date% %time% >> restart_log.txt

REM Keep window open so you can see the output
echo.
echo Press any key to close this window...
pause >nul
