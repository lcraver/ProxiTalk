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
        
        # Timer-related properties
        self.mode = "clock"  # "clock" or "timer"
        self.timer_minutes = 5  # Default timer duration
        self.timer_seconds = 0
        self.timer_remaining = 0  # Remaining time in seconds
        self.timer_running = False
        self.timer_finished = False
        self.input_mode = None  # "minutes" or "seconds" when setting timer

    def start(self):
        pass

    def update(self):
        self.t += 1
        
        # Update every 20 ticks (every 1 second if update rate is 20Hz)
        if self.t % 20 == 0:
            self.display_queue.put(("clear_base",))
            
            if self.mode == "clock":
                self.update_clock()
            elif self.mode == "timer":
                self.update_timer()
    
    def update_clock(self):
        """Update the clock display"""
        self.current_time = time.strftime("%H:%M:%S", time.localtime())
        
        # Get font and calculate position
        font = self.context["fonts"]["large_bold"]
        font_width, font_height = self.context["get_text_size"](self.current_time, font)
        
        # Draw clock
        self.display_queue.put(("draw_base_text", font, self.current_time, 
                              (self.width/2)-(font_width/2), (self.height/2)-(font_height/2)-6))
        
        # Draw mode indicator
        small_font = self.context["fonts"]["small"]
        self.display_queue.put(("draw_base_text", small_font, "CLOCK - Press T for Timer", 
                              4, 4))
        
        self.play_sfx(self.path + "tick.wav")
        
        # Play chime every minute
        if self.current_time.endswith(":00"):
            self.play_sfx(self.path + "chime.wav")
    
    def update_timer(self):
        """Update the timer display"""
        # Update timer countdown
        if self.timer_running and self.timer_remaining > 0:
            self.timer_remaining -= 1
            if self.timer_remaining == 0:
                self.timer_finished = True
                self.timer_running = False
                self.play_sfx(self.path + "chime.wav")
                self.context["run_tts"]("Timer finished!", background=True)
                
        sub_text = None
        
        # Format display text
        if self.input_mode:
            # Show timer setting interface
            display_text = f"{self.timer_minutes:02d}:{self.timer_seconds:02d}"
            if self.input_mode == "minutes":
                sub_text = "(Set Mins)"
            else:
                sub_text = "(Set Secs)"
        elif self.timer_finished:
            display_text = "TIMER FINISHED"
        elif self.timer_running:
            minutes = self.timer_remaining // 60
            seconds = self.timer_remaining % 60
            display_text = f"{minutes:02d}:{seconds:02d}"
        else:
            minutes = self.timer_remaining // 60
            seconds = self.timer_remaining % 60
            display_text = f"{minutes:02d}:{seconds:02d}"
            sub_text = "(paused)" if self.timer_remaining > 0 else ""
        
        # Draw timer display
        font = self.context["fonts"]["default"]
        font_width, font_height = self.context["get_text_size"](display_text, font)
        self.display_queue.put(("draw_base_text", font, display_text,
                              (self.width/2)-(font_width/2), 2))
        
        if sub_text:
            sub_font = self.context["fonts"]["small"]
            sub_width, sub_height = self.context["get_text_size"](sub_text, sub_font)
            self.display_queue.put(("draw_base_text", sub_font, sub_text,
                                  (self.width/2)-(sub_width/2), font_height + 6))
        
        # Draw instructions
        small_font = self.context["fonts"]["small"]
        if self.input_mode:
            instructions = [
                "Up/Down: Change value",
                "Enter: Confirm",
                "Tab: Switch field",
                "Esc: Cancel"
            ]
        elif self.timer_finished:
            instructions = [
                "R: Reset Timer",
                "C: Switch to Clock"
            ]
        else:
            instructions = [
                "Space: Start/Pause | R: Reset",
                "S: Set Timer | C: Switch to Clock"
            ]
        
        # Draw each instruction line with proper spacing
        y_offset = 32
        for i, instruction in enumerate(instructions):
            width, height = self.context["get_text_size"](instruction, small_font)
            self.display_queue.put(("draw_base_text", small_font, instruction, 
                                  self.width / 2 - width / 2, y_offset + (i * 6)))
        
        # Play tick sound for running timer
        if self.timer_running and self.timer_remaining > 0:
            self.play_sfx(self.path + "tick.wav")
        
            
    def onkeyup(self, keycode):
        # Common keys for both modes
        if keycode == "KEY_R":
            if self.mode == "timer":
                self.reset_timer()
            else:
                # Reload the app if 'R' is pressed in clock mode
                self.display_queue.put(("set_screen", "Clock", "Reloading Clock app..."))
                self.context["app_manager"].reload_app("clock")
        
        elif keycode == "KEY_ESC":
            if self.input_mode:
                # Cancel timer setting
                self.input_mode = None
            else:
                # Switch to the launcher
                self.display_queue.put(("set_screen", "Launcher", "Switching to Launcher..."))
                self.context["app_manager"].swap_app_async("clock", "launcher", update_rate_hz=20.0, delay=0.1)
        
        # Mode switching
        elif keycode == "KEY_T":
            if self.mode == "clock":
                self.switch_to_timer()
        
        elif keycode == "KEY_C":
            if self.mode == "timer":
                self.switch_to_clock()
        
        # Clock mode specific keys
        elif self.mode == "clock":
            if keycode == "KEY_ENTER":
                self.context["run_tts"](f"The current time is {self.current_time}", background=True)
        
        # Timer mode specific keys
        elif self.mode == "timer":
            if self.input_mode:
                self.handle_timer_input(keycode)
            else:
                self.handle_timer_control(keycode)
    
    def handle_timer_input(self, keycode):
        """Handle input when setting timer duration"""
        if keycode == "KEY_ENTER":
            # Confirm timer setting
            self.timer_remaining = self.timer_minutes * 60 + self.timer_seconds
            self.input_mode = None
            self.timer_finished = False
            self.context["run_tts"](f"Timer set for {self.timer_minutes} minutes and {self.timer_seconds} seconds", background=True)
        
        elif keycode == "KEY_TAB":
            # Switch between minutes and seconds
            if self.input_mode == "minutes":
                self.input_mode = "seconds"
            else:
                self.input_mode = "minutes"
        
        elif keycode == "KEY_UP" or keycode == "KEY_W":
            if self.input_mode == "minutes":
                self.timer_minutes = min(59, self.timer_minutes + 1)
            else:
                self.timer_seconds = min(59, self.timer_seconds + 1)
        
        elif keycode == "KEY_DOWN" or keycode == "KEY_S":
            if self.input_mode == "minutes":
                self.timer_minutes = max(0, self.timer_minutes - 1)
            else:
                self.timer_seconds = max(0, self.timer_seconds - 1)
    
    def handle_timer_control(self, keycode):
        """Handle timer control when not in input mode"""
        if keycode == "KEY_SPACE":
            if self.timer_finished:
                self.reset_timer()
            elif self.timer_remaining > 0:
                self.timer_running = not self.timer_running
        
        elif keycode == "KEY_S":
            if not self.timer_running:
                self.input_mode = "minutes"
                self.context["run_tts"]("Setting timer duration", background=True)
        
        elif keycode == "KEY_ENTER":
            if self.timer_remaining > 0:
                minutes = self.timer_remaining // 60
                seconds = self.timer_remaining % 60
                if self.timer_running:
                    self.context["run_tts"](f"Timer running: {minutes} minutes and {seconds} seconds remaining", background=True)
                else:
                    self.context["run_tts"](f"Timer paused: {minutes} minutes and {seconds} seconds remaining", background=True)
            else:
                self.context["run_tts"]("No timer set", background=True)
    
    def switch_to_timer(self):
        """Switch from clock to timer mode"""
        self.mode = "timer"
        if self.timer_remaining == 0:
            self.timer_remaining = self.timer_minutes * 60 + self.timer_seconds
    
    def switch_to_clock(self):
        """Switch from timer to clock mode"""
        self.mode = "clock"
        self.input_mode = None
    
    def reset_timer(self):
        """Reset the timer to its original duration"""
        self.timer_remaining = self.timer_minutes * 60 + self.timer_seconds
        self.timer_running = False
        self.timer_finished = False

    def stop(self):
        pass