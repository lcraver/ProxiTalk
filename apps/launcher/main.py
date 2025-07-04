from interfaces import AppBase
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]

    def start(self):
        print("[Launcher] Started")
        self.display_queue.put(("set_screen", "Launcher", "App started"))

    def update(self):
        pass
    
    def onkeyup(self, keycode):
        pass
    
    def stop(self):
        self.display_queue.put(("set_screen", "Launcher", "App stopped"))
        print("[Launcher] Stopped")
