import os
import sys
import subprocess
import threading
import time
import psutil
from interfaces import AppBase

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.draw = context["drawing"]
        self.width = context["screen_width"]
        self.height = context["screen_height"]
        self.fonts = context["fonts"]
        self.get_text_size = context["get_text_size"]
        
        self.selection = 0
        self.options = [
            "Restart ProxiTalk App",
            "Kill ProxiTalk Processes", 
            "Emergency Exit"
        ]
        self.descriptions = [
            "Clean restart of ProxiTalk Python application",
            "Force terminate ProxiTalk related processes",
            "Immediate exit without cleanup",
            "Return to launcher"
        ]
        
        self.confirming = False
        self.confirm_selection = 0
        self.confirm_options = ["Yes", "No"]
        
        print("[Reboot App] Initialized")
        
    def start(self):
        print("[Reboot App] Started")
        self.draw_interface()
        
    def draw_interface(self):
        """Draw the main interface"""
        # Begin batch drawing
        self.draw["begin_batch"]()
        self.draw["clear_screen"]()
        
        if self.confirming:
            self.draw_confirmation()
        else:
            self.draw_main_menu()
            
        # End batch
        self.draw["end_batch"]()
            
    def draw_main_menu(self):
        """Draw the main reboot options menu"""
        # Title
        title = "Reboot Options"
        title_width = self.get_text_size(title, self.fonts["small"])[0]
        title_x = (self.width - title_width) // 2
        self.draw["draw_text_inverted"](title, title_x, 2, self.fonts["small"])
        
        # Draw options
        y_offset = 12
        for i, option in enumerate(self.options):
            # Highlight selected option
            if i == self.selection:
                # Draw selection box
                self.draw["draw_text_inverted"](option, 2, y_offset, self.fonts["small"], 1)
            else:
                self.draw["draw_text"](option, 2, y_offset, self.fonts["small"])
            
            y_offset += 10
            
        # Draw description for selected option
        if self.selection < len(self.descriptions):
            desc = self.descriptions[self.selection]
            desc_y = self.height - 14
            
            # Word wrap description
            words = desc.split()
            lines = []
            current_line = ""
            
            for word in words:
                test_line = current_line + (" " if current_line else "") + word
                if self.get_text_size(test_line, self.fonts["small"])[0] <= self.width - 4:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            
            if current_line:
                lines.append(current_line)
            
            # Draw description lines
            for i, line in enumerate(lines[:2]):  # Max 2 lines
                self.draw["draw_text"](line, 2, desc_y + i * 8, self.fonts["small"])
                
    def draw_confirmation(self):
        """Draw confirmation dialog"""
        # Title
        title = "Confirm Action"
        title_width = self.get_text_size(title, self.fonts["small"])[0]
        title_x = (self.width - title_width) // 2
        self.draw["draw_text_inverted"](title, title_x, 2, self.fonts["small"])
        
        # Confirmation message
        action = self.options[self.selection]
        msg = f"{action}?"
        
        # Word wrap message
        words = msg.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if self.get_text_size(test_line, self.fonts["small"])[0] <= self.width - 4:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        # Draw message lines
        y_pos = 20
        for line in lines:
            self.draw["draw_text"](line, 2, y_pos, self.fonts["small"])
            y_pos += 8
            
        # Draw Yes/No options
        y_pos += 8
        for i, option in enumerate(self.confirm_options):
            if i == self.confirm_selection:
                # Draw selection box
                self.draw["draw_text_inverted"](option, 4, y_pos, self.fonts["small"])
            else:
                self.draw["draw_text"](option, 4, y_pos, self.fonts["small"])
            y_pos += 10
    
    def onkeydown(self, keycode):
        """Handle key press events"""
        if self.confirming:
            self.handle_confirmation_keys(keycode)
        else:
            self.handle_menu_keys(keycode)
            
    def handle_menu_keys(self, keycode):
        """Handle keys in main menu"""
        if keycode == "KEY_UP" or keycode == "KEY_W":
            self.selection = (self.selection - 1) % len(self.options)
            self.draw_interface()
        elif keycode == "KEY_DOWN" or keycode == "KEY_S":
            self.selection = (self.selection + 1) % len(self.options)
            self.draw_interface()
        elif keycode == "KEY_ENTER" or keycode == "KEY_SPACE":
            if self.selection == len(self.options) - 1:  # Cancel
                self.return_to_launcher()
            else:
                self.confirming = True
                self.confirm_selection = 0
                self.draw_interface()
        elif keycode == "KEY_ESC":
            self.return_to_launcher()
            
    def handle_confirmation_keys(self, keycode):
        """Handle keys in confirmation dialog"""
        if keycode == "KEY_UP" or keycode == "KEY_DOWN" or keycode == "KEY_W" or keycode == "KEY_S":
            self.confirm_selection = (self.confirm_selection + 1) % len(self.confirm_options)
            self.draw_interface()
        elif keycode == "KEY_ENTER" or keycode == "KEY_SPACE":
            if self.confirm_selection == 0:  # Yes
                self.execute_action()
            else:  # No
                self.confirming = False
                self.draw_interface()
        elif keycode == "KEY_ESC":
            self.confirming = False
            self.draw_interface()
            
    def execute_action(self):
        """Execute the selected action"""
        action_index = self.selection
        
        if action_index == 0:  # Restart ProxiTalk
            self.restart_proxitalk()
        elif action_index == 1:  # Kill All Processes
            self.kill_all_processes()
        elif action_index == 2:  # Emergency Exit
            self.emergency_exit()
            
    def restart_proxitalk(self):
        """Clean restart of ProxiTalk Python application with Windows-optimized approach"""
        # Clear and draw restart message
        self.draw["begin_batch"]()
        self.draw["clear_screen"]()
        self.draw["draw_text"]("Restarting ProxiTalk...", 2, 20, self.fonts["small"])
        self.draw["end_batch"]()
        
        print("[Reboot App] Initiating Windows-optimized restart...")
        
        # Do the restart in a separate thread to avoid blocking the UI
        def restart_thread():
            try:
                # Small delay to let UI update
                # time.sleep(0.5)
                
                # # Get the app manager and stop all apps cleanly
                # app_manager = self.context.get("app_manager")
                # if app_manager:
                #     print("[Reboot App] Stopping all apps...")
                #     try:
                #         app_manager.stop_all_apps()
                #     except Exception as e:
                #         print(f"[Reboot App] Error stopping apps: {e}")
                    
                # Stop TTS engines
                tts_manager = self.context.get("tts_manager")
                if tts_manager:
                    print("[Reboot App] Closing TTS engines...")
                    try:
                        tts_manager.close_all()
                    except Exception as e:
                        print(f"[Reboot App] Error closing TTS: {e}")
                    
                # Stop audio streams
                # try:
                #     from proxitalk import stop_audio_stream, stop_music
                #     print("[Reboot App] Stopping audio streams...")
                #     stop_audio_stream()
                #     stop_music()
                # except Exception as e:
                #     print(f"[Reboot App] Error stopping audio: {e}")
                    
                # Get paths
                python_exe = sys.executable
                script_path = os.path.abspath(sys.argv[0])
                
                print(f"[Reboot App] Python executable: {python_exe}")
                print(f"[Reboot App] Script path: {script_path}")
                
                if os.name == 'nt':  # Windows
                    print("[Reboot App] Using Windows restart method...")
                    
                    # Try batch file method first (most reliable on Windows)
                    batch_path = os.path.join(os.path.dirname(__file__), "restart_proxitalk.bat")
                    if os.path.exists(batch_path):
                        print(f"[Reboot App] Using batch restart: {batch_path}")
                        try:
                            # Launch batch file to handle restart - don't use shell=True with CREATE_NEW_CONSOLE
                            proc = subprocess.Popen([
                                'cmd', '/c', batch_path, 
                                python_exe, 
                                script_path, 
                                "3"
                            ], creationflags=subprocess.CREATE_NEW_CONSOLE)
                            print(f"[Reboot App] Batch restart launched with PID: {proc.pid}")
                            
                            # Wait a moment and verify it's still running
                            time.sleep(1)
                            if proc.poll() is None:
                                print("[Reboot App] Batch process confirmed running")
                            else:
                                print(f"[Reboot App] Batch process exited early with code: {proc.returncode}")
                                raise Exception("Batch process failed")
                                
                        except Exception as e:
                            print(f"[Reboot App] Batch restart failed: {e}")
                            # Try simple launcher
                            self._try_simple_launcher(python_exe, script_path)
                    else:
                        print("[Reboot App] Batch file not found, trying simple launcher")
                        self._try_simple_launcher(python_exe, script_path)
                        
                else:  # Linux/Unix
                    print("[Reboot App] Using Unix restart method...")
                    try:
                        subprocess.Popen([python_exe, script_path], 
                                       cwd=os.path.dirname(script_path))
                        print("[Reboot App] Unix restart launched")
                    except Exception as e:
                        print(f"[Reboot App] Unix restart failed: {e}")
                    
            except Exception as e:
                print(f"[Reboot App] Error in restart thread: {e}")
                # Try to return to launcher on error
                try:
                    if hasattr(self, 'return_to_launcher'):
                        self.return_to_launcher()
                except:
                    os._exit(1)
        
        # Start the restart process in a separate thread
        threading.Thread(target=restart_thread, daemon=True).start()
        
    def _windows_direct_restart(self, python_exe, script_path):
        """Direct Windows restart method without batch file"""
        try:
            # Method 1: Using start command through cmd
            print("[Reboot App] Trying Windows start command...")
            subprocess.Popen([
                'cmd', '/c', 'start', 'ProxiTalk', python_exe, script_path
            ], creationflags=subprocess.CREATE_NEW_CONSOLE)
            print("[Reboot App] Windows start command launched")
            return
        except Exception as e:
            print(f"[Reboot App] Start command failed: {e}")
        
        try:
            # Method 2: Direct subprocess with Windows flags
            print("[Reboot App] Trying direct subprocess...")
            subprocess.Popen([python_exe, script_path], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
                           cwd=os.path.dirname(script_path))
            print("[Reboot App] Direct subprocess launched")
            return
        except Exception as e:
            print(f"[Reboot App] Direct subprocess failed: {e}")
        
        try:
            # Method 3: Simple Popen without special flags
            print("[Reboot App] Trying simple Popen...")
            subprocess.Popen([python_exe, script_path], 
                           cwd=os.path.dirname(script_path))
            print("[Reboot App] Simple Popen launched")
            return
        except Exception as e:
            print(f"[Reboot App] All Windows restart methods failed: {e}")
            
    def _try_simple_launcher(self, python_exe, script_path):
        """Try using the simple launcher script"""
        launcher_path = os.path.join(os.path.dirname(__file__), "simple_launcher.py")
        if os.path.exists(launcher_path):
            print(f"[Reboot App] Trying simple launcher: {launcher_path}")
            try:
                proc = subprocess.Popen([
                    python_exe, launcher_path, 
                    python_exe, script_path, "3"
                ], creationflags=subprocess.CREATE_NEW_CONSOLE,
                  cwd=os.path.dirname(script_path))
                print(f"[Reboot App] Simple launcher started with PID: {proc.pid}")
                
                # Wait a moment and verify it's still running
                time.sleep(1)
                if proc.poll() is None:
                    print("[Reboot App] Simple launcher confirmed running")
                    return True
                else:
                    print(f"[Reboot App] Simple launcher exited early with code: {proc.returncode}")
                    raise Exception("Simple launcher failed")
                    
            except Exception as e:
                print(f"[Reboot App] Simple launcher failed: {e}")
        else:
            print(f"[Reboot App] Simple launcher not found: {launcher_path}")
        
        # Final fallback to direct Windows restart
        print("[Reboot App] Using direct Windows restart as final fallback")
        self._windows_direct_restart(python_exe, script_path)
        return False
        
    def kill_all_processes(self):
        """Force terminate ProxiTalk related processes using separate handler process"""
        # Clear and draw progress message
        self.draw["begin_batch"]()
        self.draw["clear_screen"]()
        self.draw["draw_text"]("Terminating ProxiTalk", 2, 20, self.fonts["small"])
        self.draw["draw_text"]("processes...", 2, 28, self.fonts["small"])
        self.draw["end_batch"]()
        
        print("[Reboot App] Force terminating ProxiTalk processes using separate handler...")
        
        # Launch separate kill handler process
        python_exe = sys.executable
        handler_path = os.path.join(os.path.dirname(__file__), "restart_handler.py")
        current_pid = os.getpid()
        
        print(f"[Reboot App] Handler path: {handler_path}")
        print(f"[Reboot App] Current PID: {current_pid}")
        
        try:
            # Launch the kill handler as a separate process
            result = subprocess.run([
                python_exe, handler_path, 
                "kill",
                "--exclude-pid", str(current_pid)
            ], timeout=30, capture_output=True, text=True)
            
            print(f"[Reboot App] Kill handler completed with return code: {result.returncode}")
            if result.stdout:
                print(f"[Reboot App] Handler output: {result.stdout}")
            if result.stderr:
                print(f"[Reboot App] Handler errors: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            print("[Reboot App] Kill handler timed out")
        except Exception as e:
            print(f"[Reboot App] Error launching kill handler: {e}")
            # Fallback to original method
            print("[Reboot App] Falling back to original kill method...")
            self._kill_processes_fallback()
        
        # Show completion message briefly
        self.draw["begin_batch"]()
        self.draw["clear_screen"]()
        self.draw["draw_text"]("Process cleanup complete", 2, 20, self.fonts["small"])
        self.draw["draw_text"]("Exiting in 3 seconds...", 2, 30, self.fonts["small"])
        self.draw["end_batch"]()
        
        # Exit after delay
        time.sleep(3)
        print("[Reboot App] Exiting after process cleanup")
        if "exit_callback" in self.context:
            self.context["exit_callback"]()
        else:
            os._exit(0)
            
    def _kill_processes_fallback(self):
        """Fallback method for killing processes if handler fails"""
        current_pid = os.getpid()
        killed_count = 0
        
        try:
            # Find all processes related to ProxiTalk
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
                    
                    # Don't kill ourselves
                    if is_proxitalk and proc_info['pid'] != current_pid:
                        print(f"[Reboot App] Terminating: PID {proc_info['pid']} - {name}")
                        
                        try:
                            # Try graceful termination first
                            proc.terminate()
                            killed_count += 1
                            
                            # Wait for graceful termination
                            try:
                                proc.wait(timeout=3)
                                print(f"[Reboot App] Process {proc_info['pid']} terminated gracefully")
                            except psutil.TimeoutExpired:
                                # Force kill if it doesn't terminate gracefully
                                print(f"[Reboot App] Force killing process {proc_info['pid']}")
                                proc.kill()
                                proc.wait(timeout=1)
                                
                        except psutil.NoSuchProcess:
                            # Process already terminated
                            pass
                        except psutil.AccessDenied:
                            print(f"[Reboot App] Access denied for process {proc_info['pid']}")
                            
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as e:
                    print(f"[Reboot App] Error checking process: {e}")
                    continue
                    
        except Exception as e:
            print(f"[Reboot App] Error during process termination: {e}")
            
        print(f"[Reboot App] Terminated {killed_count} ProxiTalk processes")
        
    def emergency_exit(self):
        """Immediate exit of ProxiTalk without cleanup"""
        print("[Reboot App] Emergency exit of ProxiTalk initiated")
        # Clear and draw exit message
        self.draw["begin_batch"]()
        self.draw["clear_screen"]()
        self.draw["draw_text"]("Emergency exit...", 2, 20, self.fonts["small"])
        self.draw["draw_text"]("No cleanup performed", 2, 28, self.fonts["small"])
        self.draw["end_batch"]()
        
        time.sleep(1)  # Brief pause to show message
        print("[Reboot App] Performing emergency exit")
        os._exit(1)
        
    def return_to_launcher(self):
        """Return to the launcher"""
        print("[Reboot App] Returning to launcher")
        app_manager = self.context["app_manager"]
        app_manager.swap_app_async("reboot", "launcher", update_rate_hz=20.0, delay=0.1)
    
    def stop(self):
        print("[Reboot App] Stopped")
