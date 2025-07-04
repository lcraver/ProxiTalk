from unicodedata import name
from interfaces import AppBase
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.context = context

    def start(self):
        print("[Info] Started")
        self.display_queue.put(("set_screen", "Info", "App started"))
        time.sleep(2)
        self.display_queue.put(("set_screen", "Info", "This is the Info app."))
        time.sleep(2)
        self.display_queue.put(("set_screen", "Info", "It provides information about the system."))
        time.sleep(2)
        # unload the Info app and switch to the Launcher app
        self.display_queue.put(("set_screen", "Info", "Switching to Launcher..."))
        # Allow time for the message to be displayed
        time.sleep(2)
        
        # Switch back to the launcher app
        if "app_manager" in self.context:
            app_manager = self.context["app_manager"]
            # Stop the current Info app
            app_manager.stop_app("info")
            # Load and start the launcher app
            if app_manager.load_app("launcher"):
                app_manager.start_app("launcher", update_rate_hz=20.0)
                print("[Info] Switched to Launcher app")
            else:
                print("[Info] Failed to load Launcher app")
        else:
            print("[Info] No app_manager available in context")

    def update(self):
        pass
    
    def onkeyup(self, keycode):
        pass
    
    def stop(self):
        self.display_queue.put(("set_screen", "Info", "App stopped"))
        print("[Info] Stopped")
