#!/usr/bin/env python3
"""
Restart Handler for ProxiTalk
This is a separate process that handles restarting ProxiTalk to avoid threading issues.
"""

import os
import sys
import subprocess
import time
import psutil
import argparse

def kill_proxitalk_processes(exclude_pid):
    """Kill all ProxiTalk related processes except the specified PID"""
    killed_count = 0
    
    print(f"[Restart Handler] Scanning for ProxiTalk processes (excluding PID {exclude_pid})...")
    
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                proc_info = proc.info
                name = proc_info['name'].lower() if proc_info['name'] else ''
                cmdline = ' '.join(proc_info['cmdline'] or []).lower()
                
                # Check if it's a ProxiTalk related process
                is_proxitalk = (
                    'proxitalk' in name or
                    'proxitalk' in cmdline or
                    ('python' in name and 'proxitalk.py' in cmdline) or
                    ('piper' in name and 'proxitalk' in cmdline) or
                    ('voicevox' in name and 'proxitalk' in cmdline) or
                    # Check for TTS processes spawned by ProxiTalk
                    (('piper' in cmdline or 'voicevox' in cmdline) and 
                     any('proxitalk' in arg for arg in (proc_info['cmdline'] or [])))
                )
                
                # Don't kill the excluded PID (and not ourselves)
                if is_proxitalk and proc_info['pid'] != exclude_pid and proc_info['pid'] != os.getpid():
                    print(f"[Restart Handler] Terminating: PID {proc_info['pid']} - {name}")
                    
                    try:
                        # Try graceful termination first
                        proc.terminate()
                        killed_count += 1
                        
                        # Wait for graceful termination
                        try:
                            proc.wait(timeout=3)
                            print(f"[Restart Handler] Process {proc_info['pid']} terminated gracefully")
                        except psutil.TimeoutExpired:
                            # Force kill if it doesn't terminate gracefully
                            print(f"[Restart Handler] Force killing process {proc_info['pid']}")
                            proc.kill()
                            proc.wait(timeout=1)
                            
                    except psutil.NoSuchProcess:
                        # Process already terminated
                        pass
                    except psutil.AccessDenied:
                        print(f"[Restart Handler] Access denied for process {proc_info['pid']}")
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception as e:
                print(f"[Restart Handler] Error checking process: {e}")
                continue
                
    except Exception as e:
        print(f"[Restart Handler] Error during process termination: {e}")
        
    print(f"[Restart Handler] Terminated {killed_count} ProxiTalk processes")
    return killed_count

def restart_proxitalk(script_path, python_exe, wait_time=3):
    """Restart ProxiTalk after waiting for cleanup"""
    print(f"[Restart Handler] Waiting {wait_time} seconds for cleanup...")
    time.sleep(wait_time)
    
    print(f"[Restart Handler] Starting new ProxiTalk instance...")
    print(f"[Restart Handler] Python executable: {python_exe}")
    print(f"[Restart Handler] Script path: {script_path}")
    
    try:
        if os.name == 'nt':  # Windows
            print("[Restart Handler] Starting on Windows...")
            subprocess.Popen([python_exe, script_path], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE,
                           cwd=os.path.dirname(script_path))
        else:  # Linux/Unix
            print("[Restart Handler] Starting on Linux...")
            subprocess.Popen([python_exe, script_path], 
                           cwd=os.path.dirname(script_path))
        
        print("[Restart Handler] New ProxiTalk instance started successfully")
        return True
        
    except Exception as e:
        print(f"[Restart Handler] Error starting new instance: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='ProxiTalk Restart Handler')
    parser.add_argument('action', choices=['restart', 'kill'], 
                       help='Action to perform: restart or kill processes')
    parser.add_argument('--script-path', required=True,
                       help='Path to the ProxiTalk main script')
    parser.add_argument('--python-exe', required=True,
                       help='Path to Python executable')
    parser.add_argument('--exclude-pid', type=int,
                       help='PID to exclude from termination (the calling process)')
    parser.add_argument('--wait-time', type=int, default=3,
                       help='Time to wait before restart (default: 3 seconds)')
    
    args = parser.parse_args()
    
    print(f"[Restart Handler] Starting with PID: {os.getpid()}")
    print(f"[Restart Handler] Action: {args.action}")
    print(f"[Restart Handler] Script path: {args.script_path}")
    print(f"[Restart Handler] Python exe: {args.python_exe}")
    print(f"[Restart Handler] Exclude PID: {args.exclude_pid}")
    
    if args.action == 'restart':
        # First kill all ProxiTalk processes except the caller
        if args.exclude_pid:
            kill_proxitalk_processes(args.exclude_pid)
        
        # Then restart ProxiTalk
        success = restart_proxitalk(args.script_path, args.python_exe, args.wait_time)
        exit_code = 0 if success else 1
        
    elif args.action == 'kill':
        # Just kill processes
        killed_count = kill_proxitalk_processes(args.exclude_pid if args.exclude_pid else -1)
        print(f"[Restart Handler] Operation complete. Killed {killed_count} processes.")
        exit_code = 0
    
    print(f"[Restart Handler] Exiting with code {exit_code}")
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
