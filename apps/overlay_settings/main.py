from interfaces import AppBase
import subprocess

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.MIN_VOL = 60
        self.MAX_VOL = 100
        self.UI_STEPS = 20
        self.VOLUME_CONTROL = "Speaker"
        self.emulator = context.get("emulator", False)
        self.current_ui_volume = self.UI_STEPS - 5
        
        actual_volume = self.ui_to_actual_volume(self.current_ui_volume)
        self.set_actual_volume(actual_volume)

    def ui_to_actual_volume(self, ui_level):
        ratio = ui_level / self.UI_STEPS
        actual = int(self.MIN_VOL + (self.MAX_VOL - self.MIN_VOL) * ratio)
        return actual

    def set_actual_volume(self, percent):
        if self.emulator:
            print(f"[Volume] Skipping set to {percent}% (Emulator)")
        else:
            subprocess.call(["amixer", "sset", self.VOLUME_CONTROL, f"{percent}%"])

    def start(self):
        print("[Launcher] Started")

    def update(self):
        pass
    
    def onkeyup(self, keycode):
        match keycode:
            case "KEY_VOLUMEUP":
                self.current_ui_volume = min(self.current_ui_volume + 1, self.UI_STEPS)
                actual_volume = self.ui_to_actual_volume(self.current_ui_volume)
                self.set_actual_volume(actual_volume)
                self.display_queue.put(("set_screen", "Volume", f"Up: {round(self.current_ui_volume / self.UI_STEPS * 100)}%"))
            case "KEY_VOLUMEDOWN":
                self.current_ui_volume = max(self.current_ui_volume - 1, 0)
                actual_volume = self.ui_to_actual_volume(self.current_ui_volume)
                self.set_actual_volume(actual_volume)
                self.display_queue.put(("set_screen", "Volume", f"Down: {round(self.current_ui_volume / self.UI_STEPS * 100)}%"))

    def stop(self):
        print("[Launcher] Stopped")