from interfaces import AppBase
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.t = 0
        self.current_time = time.strftime("%H:%M:%S", time.localtime())
        self.play_sfx = context["audio"]["play_sfx"]
        self.path = context["app_path"]
        self.width = context["screen_width"]
        self.height = context["screen_height"]

    def start(self):
        pass

    def update(self):
        self.t += 1
        
        # Update the current time every 20 ticks (ever 1 second if update rate is 20Hz)
        if self.t % 20 == 0:
            self.display_queue.put(("clear_base",))
            self.current_time = time.strftime("%H:%M:%S", time.localtime())
            # draw the clock in the middle of the screen
            
            # get font width and height
            font = self.context["fonts"]["large_bold"]
            font_width, font_height = self.context["get_text_size"](self.current_time, font)

            self.display_queue.put(("draw_base_text", font, self.current_time, (self.width/2)-(font_width/2), (self.height/2)-(font_height/2)-6))
            self.play_sfx(self.path + "tick.wav")
            # play chime every time the seconds reach 0 (every 60 seconds)
            if self.current_time.endswith(":00"):
                self.play_sfx(self.path + "chime.wav")
        
            
    def onkeyup(self, keycode):
        # reload the app if 'R' is pressed
        if keycode == "KEY_R":
            self.display_queue.put(("set_screen", "Clock", "Reloading Clock app..."))
            self.context["app_manager"].reload_app("clock")
        
        # read the current time if 'Enter' is pressed
        elif keycode == "KEY_ENTER":
            self.context["run_tts"](f"The current time is {self.current_time}", background=True)
        
        # switch to the launcher if 'Esc' is pressed
        elif keycode == "KEY_ESC":
            self.display_queue.put(("set_screen", "Launcher", "Switching to Launcher..."))
            self.context["app_manager"].swap_app_async("clock", "launcher", update_rate_hz=20.0, delay=0.1)

    def stop(self):
        pass