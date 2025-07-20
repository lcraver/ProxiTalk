import threading
import time
import traceback
from typing import Dict, List, Optional, Callable, Any
import importlib.util
import os
from interfaces import AppBase


class AppManager:
    """
    A reusable application manager that handles loading, starting, stopping,
    and managing the lifecycle of multiple applications.
    """

    def __init__(self, apps_dir: str, overlay_dir: str, context: Dict[str, Any]):
        self.apps_dir = apps_dir
        self.overlay_dir = overlay_dir
        self.context = context
        self.loaded_apps: Dict[str, AppBase] = {}
        self.app_threads: Dict[str, threading.Thread] = {}
        self.running_apps: Dict[str, bool] = {}
        self.app_cursor_preferences: Dict[str, bool] = {}  # Track cursor preferences per app
        self.active_app: Optional[str] = None  # Track the currently active non-overlay app
        self.overlay_apps: set = set()  # Track which apps are overlays
        self._stop_all = False
        
    def load_app_instance(self, app_name: str) -> Optional[AppBase]:
        """Load a single app instance from its main.py file."""
        try:
            path = os.path.join(self.apps_dir, app_name, "main.py")
            if not os.path.isfile(path):
                print(f"[AppManager] App file not found: {path}")
                return None
                
            spec = importlib.util.spec_from_file_location(f"{app_name}.main", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, "App"):
                print(f"[AppManager] No 'App' class found in {app_name}")
                return None

            self.context["app_path"] = os.path.join(self.apps_dir, app_name, "")
            app_instance = mod.App(self.context)
            if not isinstance(app_instance, AppBase):
                print(f"[AppManager] App '{app_name}' does not inherit from AppBase")
                return None
            
            return app_instance

        except Exception as e:
            print(f"[AppManager] Failed to load app '{app_name}': {e}")
            traceback.print_exc()
            return None
    
    def load_overlays(self, apps: List[Dict[str, Any]]) -> int:
        """Load all overlay-type applications from the overlays directory."""
        loaded_count = 0
        
        # Check if overlay directory exists
        if not os.path.exists(self.overlay_dir):
            print(f"[AppManager] Overlay directory not found: {self.overlay_dir}")
            return 0
            
        # Load all apps from overlay directory
        for overlay_name in os.listdir(self.overlay_dir):
            overlay_path = os.path.join(self.overlay_dir, overlay_name)
            if os.path.isdir(overlay_path):
                main_path = os.path.join(overlay_path, "main.py")
                if os.path.isfile(main_path):
                    # Load overlay app instance
                    app_instance = self.load_overlay_instance(overlay_name)
                    if app_instance:
                        self.loaded_apps[overlay_name] = app_instance
                        self.overlay_apps.add(overlay_name)  # Track as overlay
                        loaded_count += 1
                        print(f"[AppManager] Loaded overlay: {overlay_name}")
                        
        return loaded_count
    
    def load_overlay_instance(self, overlay_name: str) -> Optional[AppBase]:
        """Load a single overlay instance from its main.py file."""
        try:
            path = os.path.join(self.overlay_dir, overlay_name, "main.py")
            if not os.path.isfile(path):
                print(f"[AppManager] Overlay file not found: {path}")
                return None
                
            spec = importlib.util.spec_from_file_location(f"{overlay_name}.main", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, "App"):
                print(f"[AppManager] No 'App' class found in overlay {overlay_name}")
                return None

            self.context["app_path"] = os.path.join(self.overlay_dir, overlay_name, "")
            app_instance = mod.App(self.context)
            if not isinstance(app_instance, AppBase):
                print(f"[AppManager] Overlay '{overlay_name}' does not inherit from AppBase")
                return None
            
            return app_instance

        except Exception as e:
            print(f"[AppManager] Failed to load overlay '{overlay_name}': {e}")
            traceback.print_exc()
            return None
    
    def load_app(self, app_name: str) -> bool:
        """Load a single application by name."""
        if app_name in self.loaded_apps:
            print(f"[AppManager] App '{app_name}' already loaded")
            return True
            
        app_instance = self.load_app_instance(app_name)
        if app_instance:
            self.loaded_apps[app_name] = app_instance
            # Load and store cursor preference
            self.app_cursor_preferences[app_name] = self.get_app_cursor_preference(app_name)
            print(f"[AppManager] Loaded app: {app_name} (cursor: {self.app_cursor_preferences[app_name]})")
            return True
        return False
    
    def start_app(self, app_name: str, update_rate_hz: float = 20.0) -> bool:
        """Start an application in a background thread."""
        if app_name not in self.loaded_apps:
            print(f"[AppManager] Cannot start unloaded app: {app_name}")
            return False
            
        if app_name in self.app_threads and self.app_threads[app_name].is_alive():
            print(f"[AppManager] App '{app_name}' is already running")
            return True
        
        app_instance = self.loaded_apps[app_name]
        self.running_apps[app_name] = True
        
        # Set as active app if it's not an overlay
        if app_name not in self.overlay_apps:
            self.active_app = app_name
            print(f"[AppManager] Set active app: {app_name}")
        
        def app_loop():
            try:
                print(f"[AppManager] Starting app: {app_name}")
                # Set cursor state for this app
                self.set_app_cursor_state(app_name)
                app_instance.start()
                
                sleep_time = 1.0 / update_rate_hz
                while self.running_apps.get(app_name, False) and not self._stop_all:
                    app_instance.update()
                    time.sleep(sleep_time)
                    
            except Exception as e:
                print(f"[AppManager] Exception in app '{app_name}': {e}")
                traceback.print_exc()
            finally:
                try:
                    app_instance.stop()
                    print(f"[AppManager] Stopped app: {app_name}")
                except Exception as e:
                    print(f"[AppManager] Error stopping app '{app_name}': {e}")
                
                self.running_apps[app_name] = False

        app_thread = threading.Thread(target=app_loop, daemon=True, name=f"App-{app_name}")
        app_thread.start()
        self.app_threads[app_name] = app_thread
        
        return True
    
    def stop_app(self, app_name: str, timeout: float = 5.0) -> bool:
        """Stop a running application."""
        if app_name not in self.running_apps:
            print(f"[AppManager] App '{app_name}' was not in running_apps dict")
            return True
            
        if not self.running_apps[app_name]:
            print(f"[AppManager] App '{app_name}' was already marked as not running")
            return True
            
        print(f"[AppManager] Stopping app: {app_name}")
        self.running_apps[app_name] = False
        
        # Clear cursor when stopping an app
        self.clear_cursor()
        
        # Clear active app if this is the one being stopped
        if self.active_app == app_name:
            print(f"[AppManager] Clearing active app during stop: {app_name}")
            self.active_app = None
        
        if app_name in self.app_threads:
            thread = self.app_threads[app_name]
            print(f"[AppManager] Waiting for thread {app_name} to stop...")
            thread.join(timeout=timeout)
            
            if thread.is_alive():
                print(f"[AppManager] Warning: App '{app_name}' did not stop within {timeout}s")
                return False
            else:
                del self.app_threads[app_name]
                print(f"[AppManager] Thread for '{app_name}' stopped successfully")
        else:
            print(f"[AppManager] No thread found for app '{app_name}'")
        
        return True
    
    def restart_app(self, app_name: str, update_rate_hz: float = 20.0) -> bool:
        """Restart an application."""
        self.stop_app(app_name)
        return self.start_app(app_name, update_rate_hz)
    
    def stop_all_apps(self, timeout: float = 10.0) -> bool:
        """Stop all running applications."""
        print("[AppManager] Stopping all apps...")
        self._stop_all = True
        
        # Stop all apps
        for app_name in list(self.running_apps.keys()):
            self.running_apps[app_name] = False
        
        # Wait for all threads to finish
        all_stopped = True
        for app_name, thread in list(self.app_threads.items()):
            thread.join(timeout=timeout)
            if thread.is_alive():
                print(f"[AppManager] Warning: App '{app_name}' did not stop within {timeout}s")
                all_stopped = False
            else:
                del self.app_threads[app_name]
        
        return all_stopped
    
    def is_app_running(self, app_name: str) -> bool:
        """Check if an application is currently running."""
        return self.running_apps.get(app_name, False)
    
    def get_loaded_apps(self) -> List[str]:
        """Get list of loaded application names."""
        return list(self.loaded_apps.keys())
    
    def get_running_apps(self) -> List[str]:
        """Get list of currently running application names."""
        return [name for name, running in self.running_apps.items() if running]
    
    def distribute_event(self, event_name: str, *args, **kwargs) -> None:
        """Distribute an event to the active app and all running overlay applications."""
        # Only send events to:
        # 1. The currently active (non-overlay) app
        # 2. All overlay apps that are currently running (not just loaded)
        
        apps_to_notify = []
        
        # Add active app if it exists and is loaded
        if self.active_app and self.active_app in self.loaded_apps:
            apps_to_notify.append(self.active_app)
        
        # Add only running overlay apps (not just loaded ones)
        for overlay_name in self.overlay_apps:
            if overlay_name in self.loaded_apps and self.is_app_running(overlay_name):
                apps_to_notify.append(overlay_name)
        
        # Send events to selected apps
        for app_name in apps_to_notify:
            app_instance = self.loaded_apps[app_name]
            if hasattr(app_instance, event_name):
                try:
                    handler = getattr(app_instance, event_name)
                    handler(*args, **kwargs)
                except Exception as e:
                    print(f"[AppManager] Error in {app_name}.{event_name}: {e}")
                    traceback.print_exc()
    
    def get_event_receiving_apps(self) -> List[str]:
        """Get list of apps that would receive events (for debugging)."""
        apps_to_notify = []
        
        # Add active app if it exists and is loaded
        if self.active_app and self.active_app in self.loaded_apps:
            apps_to_notify.append(f"{self.active_app} (active)")
        
        # Add only running overlay apps
        for overlay_name in self.overlay_apps:
            if overlay_name in self.loaded_apps and self.is_app_running(overlay_name):
                apps_to_notify.append(f"{overlay_name} (overlay-running)")
        
        return apps_to_notify
    
    def debug_app_state(self):
        """Print current app state for debugging."""
        print(f"[AppManager Debug] Active app: {self.active_app}")
        print(f"[AppManager Debug] Loaded apps: {list(self.loaded_apps.keys())}")
        print(f"[AppManager Debug] Overlay apps: {list(self.overlay_apps)}")
        print(f"[AppManager Debug] Running apps: {[name for name, running in self.running_apps.items() if running]}")
        print(f"[AppManager Debug] Apps receiving events: {self.get_event_receiving_apps()}")

    def get_app_instance(self, app_name: str) -> Optional[AppBase]:
        """Get a loaded app instance by name."""
        return self.loaded_apps.get(app_name)
    
    def unload_app(self, app_name: str) -> bool:
        """Unload an application (stop it first if running)."""
        if self.is_app_running(app_name):
            if not self.stop_app(app_name):
                return False
        
        if app_name in self.loaded_apps:
            del self.loaded_apps[app_name]
            print(f"[AppManager] Unloaded app: {app_name}")
        
        return True
    
    def reload_app(self, app_name: str, update_rate_hz: float = 20.0) -> bool:
        """Reload an application (useful for development)."""
        was_running = self.is_app_running(app_name)
        
        if not self.unload_app(app_name):
            return False
        
        if not self.load_app(app_name):
            return False
        
        if was_running:
            return self.start_app(app_name, update_rate_hz)
        
        return True
    
    def swap_app(self, from_app: str, to_app: str, update_rate_hz: float = 20.0) -> bool:
        """
        Safely swap from one app to another.
        Stops and unloads the 'from_app', and starts the 'to_app'.
        
        Args:
            from_app: Name of the app to stop and unload
            to_app: Name of the app to start
            update_rate_hz: Update rate for the new app
            
        Returns:
            bool: True if swap was successful, False otherwise
        """
        print(f"[AppManager] Swapping from '{from_app}' to '{to_app}'")
        
        # Debug: Show current state before swap
        print(f"[AppManager] Before swap - Active: {self.active_app}, Loaded: {list(self.loaded_apps.keys())}")

        # Ensure the target app is loaded first
        if not self.load_app(to_app):
            print(f"[AppManager] Failed to load target app: {to_app}")
            return False

        # Stop and unload the source app
        if self.is_app_running(from_app):
            print(f"[AppManager] Stopping running app: {from_app}")
            if not self.stop_app(from_app):
                print(f"[AppManager] Failed to stop source app: {from_app}")
                return False
        else:
            print(f"[AppManager] App {from_app} was not running")

        # Clear active app if we're swapping away from it
        if self.active_app == from_app:
            print(f"[AppManager] Clearing active app: {from_app}")
            self.active_app = None

        # Ensure cursor is completely cleared between apps
        self.clear_cursor()
        # Also clear the cursor layer completely
        if "display_queue" in self.context:
            self.context["display_queue"].put(("clear_base_2",))

        # Unload the source app
        if from_app in self.loaded_apps:
            del self.loaded_apps[from_app]
            print(f"[AppManager] Unloaded app: {from_app}")
        else:
            print(f"[AppManager] App {from_app} was not loaded")

        # Debug: Show state after cleanup
        print(f"[AppManager] After cleanup - Active: {self.active_app}, Loaded: {list(self.loaded_apps.keys())}")

        # Start the target app (this will set it as active)
        if self.start_app(to_app, update_rate_hz):
            print(f"[AppManager] Successfully swapped from '{from_app}' to '{to_app}'")
            print(f"[AppManager] Final state - Active: {self.active_app}, Loaded: {list(self.loaded_apps.keys())}")
            return True
        else:
            print(f"[AppManager] Failed to start target app: {to_app}")
            return False

    def swap_app_async(self, from_app: str, to_app: str, update_rate_hz: float = 20.0, delay: float = 0.1) -> None:
        """
        Asynchronously swap from one app to another.
        This is useful when called from within an app's own thread to avoid deadlocks.
        
        Args:
            from_app: Name of the app to stop
            to_app: Name of the app to start
            update_rate_hz: Update rate for the new app
            delay: Delay before performing the swap (to allow current operations to complete)
        """
        def delayed_swap():
            time.sleep(delay)
            self.swap_app(from_app, to_app, update_rate_hz)
        
        swap_thread = threading.Thread(target=delayed_swap, daemon=True, name=f"Swap-{from_app}-to-{to_app}")
        swap_thread.start()
        print(f"[AppManager] Scheduled async swap from '{from_app}' to '{to_app}'")

    def get_app_cursor_preference(self, app_name: str) -> bool:
        """Get app's cursor preference from metadata, defaulting to False."""
        try:
            import json
            metadata_path = os.path.join(self.apps_dir, app_name, "metadata.json")
            if os.path.isfile(metadata_path):
                with open(metadata_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("cursor_enabled", False)  # Default to False if not specified
        except Exception as e:
            print(f"[AppManager] Error reading cursor preference for {app_name}: {e}")
        return False  # Default to cursor disabled
    
    def set_app_cursor_state(self, app_name: str):
        """Set the cursor state for the given app."""
        cursor_enabled = self.app_cursor_preferences.get(app_name, False)  # Default to False
        if "cursor" in self.context:
            self.context["cursor"]["set_app_enabled"](cursor_enabled)
            print(f"[AppManager] Set cursor for '{app_name}': {cursor_enabled}")
    
    def clear_cursor(self):
        """Clear cursor when stopping apps."""
        if "cursor" in self.context:
            self.context["cursor"]["set_app_enabled"](False)
            self.context["cursor"]["clear_area"]()  # Clear any remaining cursor artifacts
        
        # Also directly clear the cursor layer
        if "display_queue" in self.context:
            self.context["display_queue"].put(("clear_base_2",))
    
    def sync_overlays_with_preferences(self):
        """Sync overlay running states with user preferences"""
        user_prefs = self.context.get("user_preferences")
        if not user_prefs:
            print("[AppManager] No user preferences available for overlay sync")
            return
            
        for overlay_name in self.overlay_apps:
            is_disabled_in_prefs = user_prefs.is_overlay_disabled(overlay_name)
            is_currently_running = self.is_app_running(overlay_name)
            
            if is_disabled_in_prefs and is_currently_running:
                # Should be disabled but is running - stop it
                print(f"[AppManager] Syncing: Stopping overlay {overlay_name} (disabled in preferences)")
                self.stop_app(overlay_name)
            elif not is_disabled_in_prefs and not is_currently_running:
                # Should be enabled but is not running - start it
                print(f"[AppManager] Syncing: Starting overlay {overlay_name} (enabled in preferences)")
                self.start_app(overlay_name, update_rate_hz=20.0)
