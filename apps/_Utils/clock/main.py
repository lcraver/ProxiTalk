from interfaces import AppBase
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.drawing = context["drawing"]
        self.t = 0
        self.current_time = time.strftime("%H:%M:%S", time.localtime())
        self.play_sfx = context["audio"]["play_sfx"]
        self.path = context["app_path"]
        # Ensure path ends with separator for file access
        if not self.path.endswith(("/", "\\")):
            self.path += "/"
        self.width = context["screen_width"]
        self.height = context["screen_height"]

    def start(self):
        self.drawing["clear_screen"]()
        self.update_clock()
        self.update_helper_text()

    def update(self):
        self.t += 1
        
        # Update every 20 ticks (every 1 second if update rate is 20Hz)
        if self.t % 20 == 0:
            self.update_clock()
                
    def update_helper_text(self):
        """Update the helper text at the top of the display"""
        small_font = self.context["fonts"]["small"]
        help_text = "Enter:Speak | Esc:Exit"
        font_width, _ = self.context["get_text_size"](help_text, small_font)
        self.drawing["draw_text"](help_text, int((self.width/2)-(font_width/2)), 4, small_font)
    
    def update_clock(self):
        """Update the clock display"""
        self.current_time = time.strftime("%H:%M:%S", time.localtime())
        
        # Get font and calculate position
        font = self.context["fonts"]["large"]
        font_width, font_height = self.context["get_text_size"](self.current_time, font)
        
        # Draw clock (convert to integers)
        self.drawing["clear_area"](0, int((self.height/2)-(font_height/2)-3),
                                   self.width, font_height)
        self.drawing["draw_text"](self.current_time, 
                              int((self.width/2)-(font_width/2)), int((self.height/2)-(font_height/2)-3), font)
                        
        # Play tick sound with error handling
        try:
            self.play_sfx(self.path + "tick.wav")
        except Exception as e:
            print(f"[Clock] Error playing tick sound: {e}")
        
        # Play chime every minute
        if self.current_time.endswith(":00"):
            try:
                self.play_sfx(self.path + "chime.wav")
            except Exception as e:
                print(f"[Clock] Error playing chime sound: {e}")
    
    def onkeyup(self, keycode):
        # Handle escape key first - always allow backing out
        if keycode == "KEY_ESC":
            self.context["app_manager"].swap_app_async(
                "clock", "launcher", update_rate_hz=20.0, delay=0.1)
            return

        if keycode == "KEY_ENTER":
            self.context["tts"]["run"](f"The current time is {self.current_time}", background=True)

    def stop(self):
        pass