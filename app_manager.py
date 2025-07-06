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
    
    def __init__(self, apps_dir: str, context: Dict[str, Any]):
        self.apps_dir = apps_dir
        self.context = context
        self.loaded_apps: Dict[str, AppBase] = {}
        self.app_threads: Dict[str, threading.Thread] = {}
        self.running_apps: Dict[str, bool] = {}
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
        """Load all overlay-type applications."""
        loaded_count = 0
        for app in apps:
            if app["metadata"].get("type") == "overlay":
                app_instance = self.load_app_instance(app["name"])
                if app_instance:
                    self.loaded_apps[app["name"]] = app_instance
                    loaded_count += 1
                    print(f"[AppManager] Loaded overlay: {app['name']}")
        return loaded_count
    
    def load_app(self, app_name: str) -> bool:
        """Load a single application by name."""
        if app_name in self.loaded_apps:
            print(f"[AppManager] App '{app_name}' already loaded")
            return True
            
        app_instance = self.load_app_instance(app_name)
        if app_instance:
            self.loaded_apps[app_name] = app_instance
            print(f"[AppManager] Loaded app: {app_name}")
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
        
        def app_loop():
            try:
                print(f"[AppManager] Starting app: {app_name}")
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
            return True
            
        print(f"[AppManager] Stopping app: {app_name}")
        self.running_apps[app_name] = False
        
        if app_name in self.app_threads:
            thread = self.app_threads[app_name]
            thread.join(timeout=timeout)
            
            if thread.is_alive():
                print(f"[AppManager] Warning: App '{app_name}' did not stop within {timeout}s")
                return False
            else:
                del self.app_threads[app_name]
        
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
        """Distribute an event to all loaded applications that have the event handler."""
        for app_name, app_instance in list(self.loaded_apps.items()):
            if hasattr(app_instance, event_name):
                try:
                    handler = getattr(app_instance, event_name)
                    handler(*args, **kwargs)
                except Exception as e:
                    print(f"[AppManager] Error in {app_name}.{event_name}: {e}")
                    traceback.print_exc()
    
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

        # Ensure the target app is loaded first
        if not self.load_app(to_app):
            print(f"[AppManager] Failed to load target app: {to_app}")
            return False

        # Stop and unload the source app
        if self.is_app_running(from_app):
            if not self.stop_app(from_app):
                print(f"[AppManager] Failed to stop source app: {from_app}")
                return False

        if from_app in self.loaded_apps:
            del self.loaded_apps[from_app]
            print(f"[AppManager] Unloaded app: {from_app}")

        # Start the target app
        if self.start_app(to_app, update_rate_hz):
            print(f"[AppManager] Successfully swapped from '{from_app}' to '{to_app}'")
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
