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
        
        # Use the new swap_app_async method to switch apps safely
        if "app_manager" in self.context:
            app_manager = self.context["app_manager"]
            app_manager.swap_app_async("info", "launcher", update_rate_hz=20.0, delay=0.1)
        else:
            print("[Info] No app_manager available in context")

    def update(self):
        pass
    
    def onkeyup(self, keycode):
        pass
    
    def stop(self):
        self.display_queue.put(("set_screen", "Info", "App stopped"))
        print("[Info] Stopped")
