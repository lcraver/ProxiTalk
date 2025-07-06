from interfaces import AppBase
import subprocess
import threading
import time
from PIL import Image, ImageDraw, ImageFont

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.MIN_VOL = 60
        self.MAX_VOL = 100
        self.UI_STEPS = 20
        self.VOLUME_CONTROL = "PCM"
        self.emulator = context.get("emulator", False)
        self.current_ui_volume = self.UI_STEPS - 5
        self.brightness_level = 128  # track brightness locally
        self.display_inverted = False  # track inversion state
        
        self.clear_icon_thread = None
        self.clear_icon_lock = threading.Lock()
        self.clear_icon_stop_flag = threading.Event()
        
        self.volume_icon = context["load_icon"]("info")
        self.brightness_icon = context["load_icon"]("info_selected")
        self.font = context["fonts"]["small"]

        actual_volume = self.ui_to_actual_volume(self.current_ui_volume)
        self.set_actual_volume(actual_volume)
        
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
                self.show_volume_feedback("V:")
            case "KEY_VOLUMEDOWN":
                self.current_ui_volume = max(self.current_ui_volume - 1, 0)
                actual_volume = self.ui_to_actual_volume(self.current_ui_volume)
                self.set_actual_volume(actual_volume)
                self.show_volume_feedback("V:")
            case 'KEY_BRIGHTNESSUP':
                self.brightness_level = min(self.brightness_level + 32, 255)
                self.set_display_brightness(self.brightness_level)
                self.show_brightness_feedback("B:")
            case 'KEY_BRIGHTNESSDOWN':
                self.brightness_level = max(self.brightness_level - 32, 0)
                self.set_display_brightness(self.brightness_level)
                self.show_brightness_feedback("B:")
            case 'KEY_HOMEPAGE':  # Use F1 key for screen inversion toggle
                self.display_inverted = not self.display_inverted
                self.set_display_inverted(self.display_inverted)
                self.show_inversion_feedback("I:")

    def show_volume_feedback(self, message):
        icon = self.generate_bar_icon(self.current_ui_volume / self.UI_STEPS * 100, label=message)
        
        pos_x = 1
        pos_y = 64 - icon.height - 1  # Position at the bottom left, leaving space for the icon
        
        self.display_queue.put(("clear_overlay_area", pos_x, pos_y, icon.width, icon.height))
        self.display_queue.put(("draw_overlay_image", icon, pos_x, pos_y))
        self._start_clear_timer(pos_x, pos_y, icon.width, icon.height)

    def generate_bar_icon(self, volume_percent, width=24, height=4, label=None):
        volume_percent = max(0, min(100, volume_percent))

        label_width, label_height = self.context["get_text_size"](label, self.font) if label else (0, 0)
        label_width += 1 if label else 0  # Padding

        total_width = label_width + width
        img = Image.new("1", (total_width, height), 0)
        draw = ImageDraw.Draw(img)
        
        bar_x0 = label_width
        bar_x1 = label_width + width - 1
        
        draw.rectangle([0, 0, bar_x1, height-1], fill=0)

        # Center text vertically
        if label:
            draw.text((0, -1), label, font=self.font, fill=1)

        draw.rectangle([bar_x0, 0, bar_x1, height - 1], outline=1, fill=0)

        fill_width = int((volume_percent / 100.0) * width)
        if fill_width > 0:
            draw.rectangle([bar_x0, 0, bar_x0 + fill_width - 1, height - 1], fill=1)

        return img

    def show_brightness_feedback(self, message):
        icon = self.generate_bar_icon(self.brightness_level / 255 * 100, label=message)

        pos_x = 1
        pos_y = 64 - icon.height - 1  # Position at the bottom left, leaving space for the icon
        
        self.display_queue.put(("clear_overlay_area", pos_x, pos_y, icon.width, icon.height))
        self.display_queue.put(("draw_overlay_image", icon, pos_x, pos_y))
        self._start_clear_timer(pos_x, pos_y, icon.width, icon.height)

    def show_inversion_feedback(self, message):
        # Show inversion status as text instead of a bar
        status_text = f"{message} {'ON' if self.display_inverted else 'OFF'}"
        text_width, text_height = self.context["get_text_size"](status_text, self.font)
        
        # Create a simple text image
        img = Image.new("1", (text_width, text_height), 0)
        draw = ImageDraw.Draw(img)
        draw.text((0, 0), status_text, font=self.font, fill=1)

        pos_x = 1
        pos_y = 64 - img.height - 1  # Position at the bottom left
        
        self.display_queue.put(("clear_overlay_area", pos_x, pos_y, img.width, img.height))
        self.display_queue.put(("draw_overlay_image", img, pos_x, pos_y))
        self._start_clear_timer(pos_x, pos_y, img.width, img.height)
        
    def _start_clear_timer(self, x, y, width, height, delay=1.5):
        with self.clear_icon_lock:
            # Signal any running thread to stop
            self.clear_icon_stop_flag.set()
            if self.clear_icon_thread and self.clear_icon_thread.is_alive():
                self.clear_icon_thread.join()

            self.clear_icon_stop_flag = threading.Event()

            def clear_later():
                if not self.clear_icon_stop_flag.wait(delay):
                    self.display_queue.put(("clear_overlay_area", x, y, width, height))

            self.clear_icon_thread = threading.Thread(target=clear_later, daemon=True)
            self.clear_icon_thread.start()

    def _clear_icon_delayed(self, x, y, width, height, delay=1.5):
        time.sleep(delay)
        self.display_queue.put(("clear_overlay_area", x, y, width, height))

    def get_volume_icon(self):
        return self.volume_icon

    def get_brightness_icon(self):
        return self.brightness_icon

    def stop(self):
        print("[Launcher] Stopped")
        
    def ui_to_actual_volume(self, ui_level):
        ratio = ui_level / self.UI_STEPS
        actual = int(self.MIN_VOL + (self.MAX_VOL - self.MIN_VOL) * ratio)
        return actual

    def set_actual_volume(self, percent):
        if self.emulator:
            print(f"[Volume] Skipping set to {percent}% (Emulator)")
        else:
            subprocess.call(["amixer", "sset", self.VOLUME_CONTROL, f"{percent}%"])
            
    def set_display_brightness(self, level):
        level = max(0, min(255, level))
        # Using display contrast for brightness setting as per original code
        self.context.get("display").contrast(level)

    def set_display_inverted(self, inverted):
        self.context.get("display").invert(inverted)
