from interfaces import AppBase
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.t = 0
        self.current_time = time.strftime("%H:%M:%S", time.localtime())

    def start(self):
        print("[Clock] Started")
        self.display_queue.put(("set_screen", "Clock", "App started"))

    def update(self):
        self.t += 1
        if self.t % 20 == 0:
            self.current_time = time.strftime("%H:%M:%S", time.localtime())
            self.display_queue.put(("set_screen", "Clock", f"Current time: {self.current_time}"))
            
    def onkeyup(self, keycode):
        if keycode == "KEY_ENTER":
            self.context["run_tts"](f"The current time is {self.current_time}")
        elif keycode == "KEY_ESC":
            self.display_queue.put(("set_screen", "Launcher", "Switching to Launcher..."))
            if "app_manager" in self.context:
                app_manager = self.context["app_manager"]
                app_manager.swap_app_async("clock", "launcher", update_rate_hz=20.0, delay=0.1)
            else:
                print("[Clock] No app_manager available in context")

    def stop(self):
        self.display_queue.put(("set_screen", "Clock", "App stopped"))
        print("[Clock] Stopped")
