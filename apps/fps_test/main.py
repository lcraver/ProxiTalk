from interfaces import AppBase
import time
import threading
from PIL import Image, ImageDraw

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.width = context["screen_width"]
        self.height = context["screen_height"]
        
        # Refresh rate testing variables
        self.frame_count = 0
        self.start_time = None
        self.last_time = None
        self.last_update_time = 0  # Track last update time for rate limiting
        self.current_fps = 0
        self.average_fps = 0
        self.max_fps = 0
        self.min_fps = float('inf')
        self.fps_history = []
        self.test_running = False
        self.test_duration = 5.0  # Test for 5 seconds
        self.max_update_rate = 60.0  # Limit to 60 FPS max for reasonable testing
        
        # Visual elements
        self.flash_state = False

    def start(self):
        self.display_queue.put(("clear_base",))
        self.show_instructions()

    def show_instructions(self):
        font = self.context["fonts"]["small"]
        
        instructions = [
            "Refresh Rate Test",
            "",
            "Controls:",
            "SPACE - Start/Stop test",
            "R - Reset statistics", 
            "ESC - Exit to launcher",
            "",
            "Press SPACE to begin testing..."
        ]
        
        y_offset = 2
        for line in instructions:
            if line:
                text_width, text_height = self.context["get_text_size"](line, font)
                x_pos = (self.width - text_width) // 2
                self.display_queue.put(("draw_base_text", font, line, x_pos, y_offset))
            y_offset += text_height + 2

    def start_test(self):
        self.test_running = True
        self.frame_count = 0
        self.start_time = time.time()
        self.last_time = self.start_time
        self.last_update_time = 0  # Reset rate limiting
        self.fps_history = []
        self.max_fps = 0
        self.min_fps = float('inf')
        self.display_queue.put(("clear_base",))

    def stop_test(self):
        self.test_running = False
        if self.fps_history:
            self.average_fps = sum(self.fps_history) / len(self.fps_history)
        self.show_results()

    def show_results(self):
        font_small = self.context["fonts"]["small"]
        
        self.display_queue.put(("clear_base",))
        
        y_offset = 2
        
        # Title
        title = "Refresh Rate Test Results"
        title_width, title_height = self.context["get_text_size"](title, font_small)
        self.display_queue.put(("draw_base_text", font_small, title, 
                               (self.width - title_width) // 2, y_offset))
        y_offset += title_height + 2
        
        # Results
        results = [
            f"Average FPS: {self.average_fps:.2f}",
            f"Current FPS: {self.current_fps:.2f}",
            f"Maximum FPS: {self.max_fps:.2f}",
            f"Minimum FPS: {self.min_fps:.2f}" if self.min_fps != float('inf') else "Minimum FPS: N/A",
            f"Total Frames: {self.frame_count}",
            "",
            "Press SPACE to test again",
            "Press ESC to exit"
        ]
        
        for result in results:
            if result:
                text_width, text_height = self.context["get_text_size"](result, font_small)
                x_pos = (self.width - text_width) // 2
                self.display_queue.put(("draw_base_text", font_small, result, x_pos, y_offset))
            y_offset += text_height + 2

    def update(self):
        if not self.test_running:
            return
            
        current_time = time.time()
        
        # Rate limiting to prevent overwhelming the system
        if current_time - self.last_update_time < (1.0 / self.max_update_rate):
            return
        self.last_update_time = current_time
        
        if self.start_time is None:
            self.start_time = current_time
            self.last_time = current_time
            return
            
        # Calculate current FPS
        frame_time = current_time - self.last_time
        if frame_time > 0:
            self.current_fps = 1.0 / frame_time
            self.fps_history.append(self.current_fps)
            
            # Update max/min
            self.max_fps = max(self.max_fps, self.current_fps)
            self.min_fps = min(self.min_fps, self.current_fps)
        
        self.last_time = current_time
        self.frame_count += 1
        
        # Toggle flash state for visual feedback
        self.flash_state = not self.flash_state
        
        # Clear and draw current state
        self.display_queue.put(("clear_base",))
        
        # Create and draw background image with flashing effect
        bg_color = 1 if self.flash_state else 0  # Use 1 (white) or 0 (black) for monochrome display
        
        # Create and draw background image
        bg_img = Image.new("1", (self.width, self.height), bg_color)
        self.display_queue.put(("draw_base_image", bg_img, 0, 0))
        
        # Draw frame counter and FPS info on top of the background
        font_small = self.context["fonts"]["small"]
        
        # Frame counter (big and prominent)
        frame_text = f"Frame: {self.frame_count}"
        frame_width, frame_height = self.context["get_text_size"](frame_text, font_small)
        text_color = 0 if self.flash_state else 1  # Inverse of background for visibility
        self.display_queue.put(("draw_base_text", font_small, frame_text, 
                               (self.width - frame_width) // 2, 
                               (self.height - frame_height) // 2 - 50))
        
        # Current FPS
        fps_text = f"FPS: {self.current_fps:.1f}"
        fps_width, fps_height = self.context["get_text_size"](fps_text, font_small)
        self.display_queue.put(("draw_base_text", font_small, fps_text,
                               (self.width - fps_width) // 2,
                               (self.height - fps_height) // 2 + 20))
        
        # Test progress
        elapsed = current_time - self.start_time
        progress_text = f"Time: {elapsed:.1f}s"
        progress_width, progress_height = self.context["get_text_size"](progress_text, font_small)
        self.display_queue.put(("draw_base_text", font_small, progress_text,
                               (self.width - progress_width) // 2,
                               (self.height - progress_height) // 2 + 60))
        
        # Auto-stop after test duration
        if elapsed >= self.test_duration:
            self.stop_test()
            return
            
        # Small delay to prevent overwhelming the system and blocking input
        time.sleep(0.001)  # 1ms delay to allow input processing

    def reset_stats(self):
        self.frame_count = 0
        self.start_time = None
        self.last_time = None
        self.last_update_time = 0  # Reset rate limiting
        self.current_fps = 0
        self.average_fps = 0
        self.max_fps = 0
        self.min_fps = float('inf')
        self.fps_history = []
        self.test_running = False
        self.display_queue.put(("clear_base",))
        self.show_instructions()

    def onkeyup(self, keycode):
        if keycode == "KEY_SPACE":
            if self.test_running:
                self.stop_test()
            else:
                self.start_test()
                
        elif keycode == "KEY_R":
            self.reset_stats()
            
        # switch to the launcher if 'Esc' is pressed
        elif keycode == "KEY_ESC":
            self.display_queue.put(("set_screen", "Launcher", "Switching to Launcher..."))
            self.context["app_manager"].swap_app_async("refresh_test", "launcher", update_rate_hz=20.0, delay=0.1)
