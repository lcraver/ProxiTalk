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

    def stop(self):
        self.display_queue.put(("set_screen", "Clock", "App stopped"))
        print("[Clock] Stopped")
