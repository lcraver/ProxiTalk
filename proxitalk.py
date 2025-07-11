import os
import time
import hashlib
import subprocess
import threading
import math
import queue
import select
import atexit
import re
import platform
from PIL import Image, ImageDraw, ImageFont

# --- Constants --- #

IS_WINDOWS = platform.system() == "Windows"

# I2C settings for luma.oled (Linux only)
I2C_PORT = 1        # I2C port (usually 1 on Raspberry Pi)
I2C_ADDRESS = 0x3C  # Common I2C address for SSD1306 displays

if IS_WINDOWS:
    from config.emulator.paths import PIPER_BIN, MODEL_PATH, CACHE_DIR, APPS_DIR, ICON_DIR, AUTOCOMPLETE_PATH
    from config.emulator.paths import FONT_PATH, FONT_SMALL_PATH, FONT_BOLD_PATH
else:
    from config.paths import PIPER_BIN, MODEL_PATH, CACHE_DIR, APPS_DIR, ICON_DIR, AUTOCOMPLETE_PATH
    from config.paths import FONT_PATH, FONT_SMALL_PATH, FONT_BOLD_PATH
    
# -- Emulator Setup --- #

def is_admin():
    if not IS_WINDOWS:
        return True  # Assume admin on non-Windows
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if IS_WINDOWS:
    # use the keyboard module or mock input
    import keyboard
else:
    import evdev
    from evdev import InputDevice, categorize, ecodes

if IS_WINDOWS:
    import pygame
    import threading
    import io
    import wave

    class EmulatedDisplay:
        def __init__(self, width, height, scale=4):
            self.width = width
            self.height = height
            self.scale = scale
            self._image = Image.new("1", (width, height))
            self._inverted = False

            # pygame init done in thread
            self._update_lock = threading.Lock()
            self._pending_image = None
            self._stop_event = threading.Event()

            self._thread = threading.Thread(target=self._run_pygame_loop, daemon=True)
            self._thread.start()

        def fill(self, color):
            with self._update_lock:
                self._image.paste(255 if color else 0, [0, 0, self.width, self.height])
                self._pending_image = self._image.copy()

        def contrast(self, level):
            # No-op: pygame does not emulate contrast/brightness easily
            pass

        def invert(self, flag):
            with self._update_lock:
                self._inverted = flag
                if flag:
                    self._image = Image.eval(self._image, lambda px: 255 - px)
                else:
                    # If toggling invert off, re-paste to reset image (assuming original kept elsewhere)
                    # Here just invert again for demo (better keep original)
                    self._image = Image.eval(self._image, lambda px: 255 - px)
                self._pending_image = self._image.copy()

        def image(self, img):
            with self._update_lock:
                self._image = img.copy()
                if self._inverted:
                    self._image = Image.eval(self._image, lambda px: 255 - px)
                self._pending_image = self._image.copy()

        def show(self):
            with self._update_lock:
                self._pending_image = self._image.copy()

        def _run_pygame_loop(self):
            pygame.init()
            self.screen = pygame.display.set_mode((self.width * self.scale, self.height * self.scale))
            pygame.display.set_caption("ProxiTalk Emulated Display")
            clock = pygame.time.Clock()

            while not self._stop_event.is_set():
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self._stop_event.set()

                with self._update_lock:
                    if self._pending_image:
                        img = self._pending_image
                        size = img.size

                        # Convert to RGB for pygame compatibility
                        img_rgb = img.convert("RGB")
                        data = img_rgb.tobytes()
                        surface = pygame.image.fromstring(data, size, "RGB")
                        surface = pygame.transform.scale(surface, (self.width * self.scale, self.height * self.scale))
                        self.screen.blit(surface, (0, 0))
                        pygame.display.flip()
                        self._pending_image = None

                clock.tick(12)  # Limit to 12 FPS

        def stop(self):
            self._stop_event.set()
            self._thread.join()
            pygame.quit()

    # Replace real display with emulated one
    disp = EmulatedDisplay(128, 64)
else:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1309
    
    # Create I2C interface and SSD1309 device
    serial = i2c(port=I2C_PORT, address=I2C_ADDRESS)
    luma_device = ssd1309(serial)
    
    # Create compatibility wrapper for luma.oled
    class LumaDisplayWrapper:
        def __init__(self, device):
            self.device = device
            self.width = device.width
            self.height = device.height
            
        def fill(self, color):
            """Clear the display with the specified color (0 or 255)"""
            # Create a blank image and display it
            blank_image = Image.new("1", (self.width, self.height), color)
            self.device.display(blank_image)
            
        def show(self):
            """Update the display - no-op for luma.oled as display() handles this"""
            pass
            
        def image(self, img):
            """Display a PIL image on the device"""
            self.device.display(img)
            
        def stop(self):
            """Cleanup the display"""
            self.device.cleanup()
            
        def contrast(self, level):
            """Set contrast - luma.oled does not support this directly"""
            self.device.contrast(level)
            pass
    
    disp = LumaDisplayWrapper(luma_device)

disp.contrast(255)


# --- Application Setup --- #

import importlib.util
import json
import traceback
from interfaces import AppBase

apps = []
loaded_apps = {}

def load_apps():
    apps = []
    for folder in os.listdir(APPS_DIR):
        main_path = os.path.join(APPS_DIR, folder, "main.py")
        if os.path.isfile(main_path):
            apps.append({
                "name": folder,
                "metadata": load_metadata(folder),
                "icon_normal": load_icon(folder),
                "icon_selected": load_icon(folder, "selected"),
                "path": main_path,
            })
    return apps

def load_icon(app_name, state=None):
    if state:
        icon_path = os.path.join(APPS_DIR, app_name, f"icon_{state}.png")
    else:
        icon_path = os.path.join(APPS_DIR, app_name, "icon.png")
        
    if os.path.isfile(icon_path):
        return Image.open(icon_path).convert("1")
    
    return None

def load_metadata(app_name):
    metadata_path = os.path.join(APPS_DIR, app_name, "metadata.json")
    default = {"name": app_name, "version": "unknown", "type": "app", "description": "", "author": "Unknown"}

    if os.path.isfile(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**default, **data}
        except Exception as e:
            print(f"[Metadata] Failed to load metadata for {app_name}: {e}", flush=True)

    return default

def load_app_instance(app_name, context):
    try:
        path = os.path.join(APPS_DIR, app_name, "main.py")
        spec = importlib.util.spec_from_file_location(f"{app_name}.main", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if not hasattr(mod, "App"):
            raise AttributeError("No 'App' class found")

        app_instance = mod.App(context)
        if not isinstance(app_instance, AppBase):
            print(f"[Error] {app_name}'s App is not an AppBase subclass")
        else:
            loaded_apps[app_name] = app_instance
            return app_instance

    except Exception:
        print(f"[Error] Failed to load app '{app_name}':", flush=True)
        traceback.print_exc()

    return None

apps = load_apps()

# --- Icons --- #

icons = {}
# Cache for converted icons to avoid repeated mode conversions
_icon_cache = {}

def load_base_icon(name, state=None):
    cache_key = (name, state)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]
        
    path = os.path.join(ICON_DIR, name)
    
    if state:
        img = Image.open(path + "_" + state + ".png").convert("1")
    else:
        img = Image.open(path + ".png").convert("1")

    # Cache the converted icon
    _icon_cache[cache_key] = img
    return img

def load_icon(app_name, state=None):
    cache_key = (app_name, state)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]
        
    if state:
        icon_path = os.path.join(APPS_DIR, app_name, f"icon_{state}.png")
    else:
        icon_path = os.path.join(APPS_DIR, app_name, "icon.png")
        
    if os.path.isfile(icon_path):
        img = Image.open(icon_path).convert("1")
        # Cache the converted icon
        _icon_cache[cache_key] = img
        return img
    
    return None

searching_icon = load_base_icon("info")
generating_icon = load_base_icon("settings")
speaking_icon = load_base_icon("notes")

# --- Audio Playback --- #

def play_sfx_internal(path: str):
    if not os.path.isfile(path):
        print(f"[Audio] File not found: {path}", flush=True)
        return

    try:
        if IS_WINDOWS:
            sound = pygame.mixer.Sound(path)
            channel = sound.play()
            while channel.get_busy():
                pygame.time.wait(10)
        else:
            subprocess.call(["aplay", path])
    except Exception as e:
        print(f"[Audio] Error playing wav file '{path}': {e}", flush=True)
        
def play_sfx(path: str):
    threading.Thread(target=play_sfx_internal, args=(path,), daemon=True).start()


# --- Music --- #

class MusicManager:
    def __init__(self):
        self.current_music = None
        self.is_playing = False
        self.volume = 0.3
        self.music_thread = None
        self._stop_event = threading.Event()
        
    def play_music(self, path: str, loop: bool = True):
        if not os.path.isfile(path):
            print(f"[Music] File not found: {path}", flush=True)
            return
            
        self.stop_music()
        self._stop_event.clear()
        self.current_music = path
        self.is_playing = True
        
        if IS_WINDOWS:
            self.music_thread = threading.Thread(
                target=self._play_music_loop, 
                args=(path, loop), 
                daemon=True
            )
            self.music_thread.start()
    
    def _play_music_loop(self, path: str, loop: bool):
        try:
            while not self._stop_event.is_set() and self.is_playing:
                sound = pygame.mixer.Sound(path)
                sound.set_volume(self.volume)
                channel = sound.play()
                
                # Wait for the sound to finish or stop event
                while channel.get_busy() and not self._stop_event.is_set():
                    pygame.time.wait(100)
                
                if not loop:
                    break
                    
        except Exception as e:
            print(f"[Music] Error playing music '{path}': {e}", flush=True)
        finally:
            self.is_playing = False
    
    def stop_music(self):
        self.is_playing = False
        self._stop_event.set()
        if self.music_thread and self.music_thread.is_alive():
            self.music_thread.join(timeout=1.0)
        self.current_music = None
    
    # Set music volume (0.0 to 1.0)
    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, volume))
    
    def is_music_playing(self):
        return self.is_playing

# Global music manager
music_manager = MusicManager()

def play_music(path: str, loop: bool = True):
    music_manager.play_music(path, loop)

def stop_music():
    music_manager.stop_music()

def set_music_volume(volume: float):
    music_manager.set_volume(volume)


# --- Piper TTS --- #

if IS_WINDOWS:
    class PersistentPiper:
        def __init__(self, piper_path, model_path):
            self.piper_path = piper_path
            self.model_path = model_path
            self.process = None
            self.lock = threading.Lock()
            self.output_buffer = bytearray()
            self._stop_event = threading.Event()
            self.reader_thread = None
            self.start_process()

        def _read_stdout(self):
            while not self._stop_event.is_set():
                try:
                    chunk = self.process.stdout.read(1024)
                    if chunk:
                        self.output_buffer.extend(chunk)
                    else:
                        time.sleep(0.01)
                except Exception as e:
                    print(f"[Piper] stdout read error: {e}")
                    break

        def start_process(self):
            self._stop_event.clear()
            self.output_buffer = bytearray()
            try:
                self.process = subprocess.Popen(
                    [self.piper_path, "--sentence_silence", "0.1", "--model", self.model_path, "--output-raw"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                    creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
                )
            except Exception as e:
                print(f"[Piper] Failed to start: {e}")
                return

            self.reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
            self.reader_thread.start()

            # Optional: log stderr in background
            threading.Thread(target=self._log_stderr, daemon=True).start()

        def _log_stderr(self):
            for line in iter(self.process.stderr.readline, b''):
                print("Piper stderr:", line.decode(errors="ignore").strip(), flush=True)

        def synthesize(self, text, timeout=5.0):
            with self.lock:
                if not self.process or self.process.poll() is not None:
                    print("[Piper] Process not running. Restarting.", flush=True)
                    self.start_process()

                self.output_buffer.clear()

                try:
                    self.process.stdin.write(text.encode("utf-8") + b"\n")
                    self.process.stdin.flush()
                except Exception as e:
                    print(f"[Piper] Failed to send text: {e}")
                    return b''

                # Wait for output to accumulate
                start = time.time()
                while time.time() - start < timeout:
                    if len(self.output_buffer) > 0:
                        time.sleep(0.1)  # give it a moment to finish
                        break
                    time.sleep(0.05)

                return bytes(self.output_buffer)

        def close(self):
            self._stop_event.set()
            try:
                if self.process:
                    self.process.stdin.close()
                    self.process.stdout.close()
                    self.process.stderr.close()
                    self.process.terminate()
                    self.process.wait(timeout=2)
            except Exception as e:
                print(f"[Piper] Cleanup error: {e}")
else:
    class PersistentPiper:
        def __init__(self, piper_path, model_path):
            self.piper_path = piper_path
            self.model_path = model_path
            self.process = None
            self.lock = threading.Lock()
            self.start_process()

        def _drain_stderr(self):
            for line in iter(self.process.stderr.readline, b''):
                print("Piper stderr:", line.decode(errors="ignore"), flush=True)

        def start_process(self):
            self.process = subprocess.Popen(
                [self.piper_path, "--sentence_silence", "0.1", "--model", self.model_path, "--output-raw"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            threading.Thread(target=self._drain_stderr, daemon=True).start()

        def synthesize(self, text):
            with self.lock:
                if not self.process or self.process.poll() is not None:
                    print("Piper process not running. Restarting.")
                    self.start_process()

                try:
                    self.process.stdin.write(text.encode('utf-8') + b'\n')
                    self.process.stdin.flush()
                except Exception as e:
                    print("Failed to write to Piper:", e)
                    return b''

                output = b''
                start_time = time.time()
                max_wait = 4.0

                while time.time() - start_time < max_wait:
                    if self.process.stdout.closed:
                        break
                    rlist, _, _ = select.select([self.process.stdout], [], [], 0.1)
                    if rlist:
                        chunk = self.process.stdout.read(1024)
                        if not chunk:
                            break
                        output += chunk
                    elif output:
                        break  # Stop if output has begun but no more is arriving

                # In synthesize():
                if not output:
                    print("Empty audio. Restarting Piper.")
                    self.close()
                    self.start_process()

                return output

        def close(self):
            if self.process:
                try:
                    self.process.stdin.close()
                    self.process.stdout.close()
                    self.process.stderr.close()
                    self.process.terminate()
                    self.process.wait(timeout=1)
                except Exception as e:
                    print("Error closing Piper:", e, flush=True)

# --- Display Setup --- #

draw_lock = threading.RLock()
display_queue = queue.Queue()

width = disp.width
height = disp.height

# Create layered images
base_layer = Image.new("1", (width, height))        # Static screen content
base_layer_2 = Image.new("1", (width, height))      # Alternative static content (e.g., clock)
overlay_layer = Image.new("1", (width, height))     # Temporary overlays (icons, cursors)
composite_layer = Image.new("1", (width, height))   # Final image sent to display

# Drawing contexts for each layer
base_draw = ImageDraw.Draw(base_layer)
base_draw_2 = ImageDraw.Draw(base_layer_2)
overlay_draw = ImageDraw.Draw(overlay_layer)
composite_draw = ImageDraw.Draw(composite_layer)

# Font setup
padding = 2
top = padding
bottom = height - padding
bodyLineHeight = 4
x = 0

# Load fonts once and check existence
def load_fonts():
    required_fonts = [
        (FONT_PATH, "Font file"),
        (FONT_BOLD_PATH, "Bold font file"), 
        (FONT_SMALL_PATH, "Small font file")
    ]
    
    for path, name in required_fonts:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{name} not found: {path}")

load_fonts()

bodyFontSize = 12

font = ImageFont.truetype(FONT_PATH, bodyFontSize)
fontBold = ImageFont.truetype(FONT_BOLD_PATH, bodyFontSize)

fontLargeSize = 24
fontLarge = ImageFont.truetype(FONT_PATH, fontLargeSize)
fontLargeBold = ImageFont.truetype(FONT_BOLD_PATH, fontLargeSize)
fontSmall = ImageFont.truetype(FONT_SMALL_PATH, 4)

# --- Render composite display --- #
# Track if display needs updating to avoid unnecessary redraws
display_dirty = True

def update_display(force=False):
    global display_dirty
    if not display_dirty and not force:
        return
        
    with draw_lock:
        composite_layer.paste(base_layer)
        composite_layer.paste(base_layer_2, (0, 0), base_layer_2)
        composite_layer.paste(overlay_layer, (0, 0), overlay_layer)
        disp.image(composite_layer)
        disp.show()
        display_dirty = False

def mark_display_dirty():
    global display_dirty
    display_dirty = True

# --- Display Functions (modified to use layers) --- #

# Wrap text to fit screen width with caching
_text_wrap_cache = {}

def wrap_text_by_pixel_width(text, font, max_width):
    # Use cache key to avoid recalculating same text
    cache_key = (text, font, max_width)
    if cache_key in _text_wrap_cache:
        return _text_wrap_cache[cache_key]
    
    words = text.split(' ')
    lines = []
    current_line = ""

    for word in words:
        test_line = current_line + (" " if current_line else "") + word
        width = base_draw.textlength(test_line, font=font)
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            # Only do character-by-character if word is actually too long
            word_width = base_draw.textlength(word, font=font)
            if word_width > max_width:
                partial_word = ""
                for char in word:
                    test_partial = partial_word + char
                    if base_draw.textlength(test_partial, font=font) <= max_width:
                        partial_word = test_partial
                    else:
                        lines.append(partial_word)
                        partial_word = char
                if partial_word:
                    current_line = partial_word
            else:
                current_line = word

    if current_line:
        lines.append(current_line)

    # Cache result (limit cache size to prevent memory bloat)
    if len(_text_wrap_cache) > 100:
        _text_wrap_cache.clear()
    _text_wrap_cache[cache_key] = lines
    
    return lines

# Cursor state management
cursor_width = 0  # Width of the cursor in pixels
cursor_height = bodyLineHeight + 1
lastDrawX = 0
lastDrawY = 0
prevDrawX = 0  # Previous cursor X position
prevDrawY = 0  # Previous cursor Y position
cursor_enabled = True  # Global cursor enable/disable
current_app_cursor_enabled = False  # Current app's cursor preference (default to False)
cursor_state_changed = False  # Track if cursor state needs updating
last_cursor_visible_state = False  # Track last visible state to avoid redundant updates

def display_set_screen(title, text):
    global lastDrawX, lastDrawY, prevDrawX, prevDrawY
    with draw_lock:
        base_draw.rectangle((0, 0, width, height), outline=0, fill=0)
        # Clear the cursor layer as well when setting a new screen
        base_draw_2.rectangle((0, 0, width, height), outline=0, fill=0)
        
        wrapped_lines = wrap_text_by_pixel_width(text, fontSmall, width-4)
        title_width = math.ceil(base_draw.textlength(title, fontSmall))
        title_top = top
        title_height = fontSmall.getsize(title)[1]
        base_draw.text((x + width/2 - title_width/2, title_top), title, font=fontSmall, fill=255)

        startY = top + title_height + padding
        max_lines = (height - startY) // bodyLineHeight
        for i in range(min(len(wrapped_lines), max_lines)):
            base_draw.text((x, startY + i * bodyLineHeight), wrapped_lines[i], font=fontSmall, fill=255)
            # Store previous position before updating
            prevDrawY = lastDrawY
            prevDrawX = lastDrawX
            # Update cursor position
            lastDrawY = startY + i * bodyLineHeight
            lastDrawX = base_draw.textlength(wrapped_lines[i], font=fontSmall)
        mark_display_dirty()
        # Force immediate update for screen changes to prevent black screens
        update_display(force=True)

def display_draw_text(layer, font, text, x=0, y=0):
    with draw_lock:
        layer.text((x, y), text, font=font, fill=255)
        mark_display_dirty()

def display_draw_icon(layer, icon_img, x=0, y=height - 8):
    with draw_lock:
        # Icon should already be converted to mode "1" from cache
        if icon_img and icon_img.mode != "1":
            icon_img = icon_img.convert("1")
        if icon_img:
            layer.paste(icon_img, (x, y), icon_img)
        mark_display_dirty()

def display_clear_area(layer, x=0, y=0, width=128, height=64):
    with draw_lock:
        layer.rectangle((x, y, x + width, y + height), fill=0)
        mark_display_dirty()

def display_draw_blinking_cursor(x, y, isOn):
    global current_app_cursor_enabled, cursor_state_changed, last_cursor_visible_state, prevDrawX, prevDrawY
    with draw_lock:
        # Check if cursor should be visible
        cursor_should_be_visible = cursor_enabled and current_app_cursor_enabled
        
        # Clear previous cursor position if position changed
        if (int(x) != int(prevDrawX) or int(y) != int(prevDrawY)) and cursor_should_be_visible:
            # Clear old cursor position
            base_draw_2.rectangle((int(prevDrawX)+2, int(prevDrawY), int(prevDrawX)+3, int(prevDrawY)+cursor_height), fill=0)
            prevDrawX = x
            prevDrawY = y
        
        # Only update if state actually changed or forced by isOn parameter
        if cursor_should_be_visible != last_cursor_visible_state or cursor_state_changed:
            if cursor_should_be_visible:
                color = 255 if isOn else 0
                base_draw_2.rectangle((int(x) + 1, int(y), int(x) + 1 + cursor_width, int(y) + cursor_height), fill=color)
            else:
                # Clear cursor area when disabled
                base_draw_2.rectangle((int(x) + 1, int(y), int(x) + 1 + cursor_width, int(y) + cursor_height), fill=0)
            
            last_cursor_visible_state = cursor_should_be_visible
            cursor_state_changed = False
            mark_display_dirty()
        elif cursor_should_be_visible:
            # Only blink if cursor is visible
            color = 255 if isOn else 0
            base_draw_2.rectangle((int(x) + 1, int(y), int(x) + 1 + cursor_width, int(y) + cursor_height), fill=color)
            mark_display_dirty()

def set_cursor_enabled(enabled):
    """Enable or disable cursor globally"""
    global cursor_enabled, cursor_state_changed
    if cursor_enabled != enabled:
        cursor_enabled = enabled
        cursor_state_changed = True
        print(f"[Cursor] Global cursor set to: {enabled}")

def set_app_cursor_enabled(enabled):
    """Enable or disable cursor for the current app"""
    global current_app_cursor_enabled, cursor_state_changed
    if current_app_cursor_enabled != enabled:
        current_app_cursor_enabled = enabled
        cursor_state_changed = True
        print(f"[Cursor] App cursor set to: {enabled}")
        
        # If disabling cursor, immediately clear the cursor area
        if not enabled:
            with draw_lock:
                base_draw_2.rectangle((0, 0, width, height), outline=0, fill=0)
                mark_display_dirty()

def set_cursor_position(x, y):
    """Set cursor position"""
    global lastDrawX, lastDrawY, prevDrawX, prevDrawY
    # Store previous position before updating
    prevDrawX = lastDrawX
    prevDrawY = lastDrawY
    # Set new position
    lastDrawX = x
    lastDrawY = y

def clear_cursor_area():
    """Clear cursor area completely"""
    global lastDrawX, lastDrawY, prevDrawX, prevDrawY
    with draw_lock:
        # Clear current cursor position
        base_draw_2.rectangle((int(lastDrawX)+1, int(lastDrawY), int(lastDrawX)+1+cursor_width, int(lastDrawY)+cursor_height), fill=0)
        # Clear previous cursor position if different
        if prevDrawX != lastDrawX or prevDrawY != lastDrawY:
            base_draw_2.rectangle((int(prevDrawX)+1, int(prevDrawY), int(prevDrawX)+1+cursor_width, int(prevDrawY)+cursor_height), fill=0)
        mark_display_dirty()

# --- Display Thread --- #

def display_thread_func():
    print("[Display Thread] Started", flush=True)
    is_cursor_on = False
    last_cursor_update = 0
    last_display_update = 0

    try:
        while True:
            timeout = 0.1

            try:
                cmd = display_queue.get(timeout=timeout)
            except queue.Empty:
                cmd = None

            if cmd:
                # print(f"[Display] Command received: {cmd}", flush=True)
                match cmd[0]:
                    case "draw_base_text":
                        _, font, text, x, y = cmd
                        display_draw_text(base_draw, font, text, x, y)
                    case "draw_overlay_text":
                        _, font, text, x, y = cmd
                        display_draw_text(overlay_draw, font, text, x, y)
                    case "draw_base_image":
                        _, img, x, y = cmd
                        display_draw_icon(base_layer, img, x, y)
                    case "draw_overlay_image":
                        _, img, x, y = cmd
                        display_draw_icon(overlay_layer, img, x, y)
                    case "clear_base":
                        display_clear_area(base_draw, 0, 0, 128, 64)
                        # Force immediate update for full screen clears
                        update_display(force=True)
                    case "clear_base_2":
                        display_clear_area(base_draw_2, 0, 0, 128, 64)
                        # Force immediate update for cursor layer clears
                        update_display(force=True)
                    case "clear_base_area":
                        _, x, y, width, height = cmd
                        display_clear_area(base_draw, x, y, width, height)
                    case "clear_overlay_area":
                        _, x, y, width, height = cmd
                        display_clear_area(overlay_draw, x, y, width, height)
                    case "draw_cursor":
                        _, x, y, isOn = cmd
                        display_draw_blinking_cursor(x, y, isOn)
                    case "set_cursor_enabled":
                        _, enabled = cmd
                        set_cursor_enabled(enabled)
                    case "set_app_cursor_enabled":
                        _, enabled = cmd
                        set_app_cursor_enabled(enabled)
                    case "set_cursor_position":
                        _, x, y = cmd
                        set_cursor_position(x, y)
                    case "clear_cursor_area":
                        clear_cursor_area()
                    case "exit":
                        print("[Display Thread] Exiting on exit command", flush=True)
                        break

            now = time.time()
            # Cursor blinking - only if cursor is enabled and visible
            cursor_should_be_visible = cursor_enabled and current_app_cursor_enabled
            if cursor_should_be_visible and now - last_cursor_update > 0.5:
                is_cursor_on = not is_cursor_on
                display_draw_blinking_cursor(lastDrawX, lastDrawY, is_cursor_on)
                last_cursor_update = now
            elif cursor_state_changed:
                # Handle cursor state changes immediately
                display_draw_blinking_cursor(lastDrawX, lastDrawY, False)
            
            update_display()
            last_display_update = now

    except Exception as e:
        print(f"[Display Thread] Crashed with exception: {e}", flush=True)

# --- TTS + Cache --- #

os.makedirs(CACHE_DIR, exist_ok=True)

from config.wordmap import word_map

piper_instance = PersistentPiper(PIPER_BIN, MODEL_PATH)
atexit.register(lambda: piper_instance.close())

def apply_word_map(text, word_map):
    # Use regex to replace whole words only
    def replacer(match):
        word = match.group(0)
        # Case insensitive replacement, preserve case if you want (optional)
        replacement = word_map.get(word.lower(), word)
        return replacement

    pattern = re.compile(r'\b\w+\b')
    return pattern.sub(replacer, text)

def hash_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

# Initialize Pygame mixer if running on Windows
if IS_WINDOWS:
    pygame.mixer.init(frequency=22050, size=-16, channels=1)

def wrap_raw_audio_as_wav(raw_bytes, sample_rate=22050):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(raw_bytes)
    buffer.seek(0)
    return buffer

def play_audio_sync(audio_bytes):
    if IS_WINDOWS:
        try:
            wav_buf = wrap_raw_audio_as_wav(audio_bytes)
            sound = pygame.mixer.Sound(wav_buf)
            channel = sound.play()
            while channel.get_busy():
                pygame.time.wait(10)
        except Exception as e:
            print(f"[Audio] Pygame playback error: {e}", flush=True)
    else:
        try:
            proc = subprocess.Popen([
                "timeout", "5",
                "aplay", "-R", "400", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"
            ], stdin=subprocess.PIPE)
            proc.communicate(input=audio_bytes)
        except Exception as e:
            print(f"[Audio] aplay error: {e}", flush=True)

def run_tts(text, background=False):
    if not text.strip():
        return
    
    cached_file = os.path.join(CACHE_DIR, hash_text(text) + ".raw")

    if os.path.exists(cached_file):
        with open(cached_file, "rb") as f:
            audio_data = f.read()

        if not background:
            display_queue.put(("set_screen", "Cached", text))
            display_queue.put(("draw_icon", speaking_icon, 0, height - 8))
        play_thread = threading.Thread(target=play_audio_sync, args=(audio_data,))
        play_thread.start()
        play_thread.join()
        if not background:
            display_queue.put(("clear_icon",))

    else:
        if not background:
            display_queue.put(("set_screen", "Generating", text))
            display_queue.put(("draw_icon", generating_icon, 0, height - 8))

        try:
            mappedText = apply_word_map(text, word_map)
            raw_audio = piper_instance.synthesize(mappedText)
            if not background:
                display_queue.put(("clear_icon",))

            if raw_audio:
                with open(cached_file, "wb") as f:
                    f.write(raw_audio)

                if not background:
                    display_queue.put(("set_screen", "Talking", text))
                    display_queue.put(("draw_icon", speaking_icon, 0, height - 8))
                play_thread = threading.Thread(target=play_audio_sync, args=(raw_audio,))
                play_thread.start()
                play_thread.join()
                if not background:
                    display_queue.put(("clear_icon",))
            else:
                if not background:
                    display_queue.put(("clear_icon",))
                    display_queue.put(("set_screen", "Error", "No audio generated"))
        except Exception as e:
            if not background:
                display_queue.put(("clear_icon",))
                display_queue.put(("set_screen", "Error", "TTS Generation Failed"))
            print(f"Error generating or playing TTS: {e}", flush=True)

# --- Input --- #

from config.keymap import shift_key_map

def find_keyboard():
    devices = [InputDevice(path) for path in evdev.list_devices()]
    print(f"Devices found: {[device.name for device in devices]}", flush=True)
    for device in devices:
        print(f"Checking device: {device.name} at {device.path}", flush=True)
        if 'mouse' in device.name.lower() or 'touchpad' in device.name.lower():
            print("Skipping mouse/touchpad device", flush=True)
            continue
        if 'keyboard' in device.name.lower():
            display_queue.put(("set_screen", "Connecting", f"Found Keyboard: {device.name}"))
            print(f"Keyboard found: {device.name} at {device.path}", flush=True)
            return device
    print("No keyboard found in devices", flush=True)
    return None


if IS_WINDOWS:
    import keyboard
    from config.emulator.win_keycodes import WIN_TO_LINUX_KEYCODE

    class ecodes:
        EV_KEY = 1

    EV_KEY = ecodes.EV_KEY
    KEY_DOWN = 1
    KEY_UP = 0

    class EvdevLikeEvent:
        def __init__(self, kb_event):
            self.type = EV_KEY
            self.code = kb_event.scan_code
            self.value = KEY_DOWN if kb_event.event_type == "down" else KEY_UP
            self.name = kb_event.name

    class KeyEvent:
        # Similar to evdev.KeyEvent
        def __init__(self, event):
            self.event = event
            self.scancode = event.code
            self.keystate = event.value  # 1=down, 0=up

        @property
        def keycode(self):
            # Map the Windows keyboard event name to Linux KEY_* string
            keyname = self.event.name.lower()
            return WIN_TO_LINUX_KEYCODE.get(keyname, self.event.name.upper())
        
        def __repr__(self):
            return f"<KeyEvent keycode={self.keycode} keystate={self.keystate}>"

    def categorize(event):
        # Only handle EV_KEY events for now
        if event.type == EV_KEY:
            return KeyEvent(event)
        return event

    class WindowsInputDevice:
        def read_loop(self):
            while True:
                kb_event = keyboard.read_event()
                if kb_event.event_type in ("down", "up"):
                    yield EvdevLikeEvent(kb_event)

    def wait_for_keyboard():
        return WindowsInputDevice()
else:
    import evdev
    def wait_for_keyboard(max_retries=24, retry_delay=2.5):
        tries = 0
        display_queue.put(("set_screen", "Connecting", "Looking for keyboard..."))
        display_queue.put(("draw_icon", searching_icon, 0, height - 8))

        while tries < max_retries or max_retries == -1:
            dev = find_keyboard()
            if dev:
                display_queue.put(("clear_icon",))
                print(f"Keyboard found: {dev.name} at {dev.path}", flush=True)
                return dev

            tries += 1
            time.sleep(retry_delay)

        return None

# Utility function for getting text dimensions using modern getbbox method
def get_text_size(text, font):
    """
    Get text width and height using the modern getbbox method.
    Returns (width, height) tuple for compatibility with the old textsize method.
    """
    # Handle None or empty text
    if not text:
        return 0, 0
        
    from PIL import ImageDraw
    # Create a temporary image to get text bbox
    temp_img = Image.new("1", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    bbox = temp_draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return width, height

def main():
    # Start display thread
    disp_thread = threading.Thread(target=display_thread_func, daemon=True)
    disp_thread.start()
    
    # Ensure required files and folders exist
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)

    # Create autocomplete words file if missing
    if not os.path.exists(AUTOCOMPLETE_PATH):
        with open(AUTOCOMPLETE_PATH, "w", encoding="utf-8") as f:
            f.write("hello\nworld\nsample\n")

    # Check if Piper binary and model exist
    if not os.path.isfile(PIPER_BIN):
        display_queue.put(("set_screen", "Error", f"Piper binary not found at:\n{PIPER_BIN}"))
        time.sleep(5)
    if not os.path.isfile(MODEL_PATH):
        display_queue.put(("set_screen", "Error", f"Model not found at:\n{MODEL_PATH}"))
        time.sleep(5)

    display_queue.put(("set_screen", "Starting", "Please wait..."))

    currentline = ""

    shift_key = 'KEY_LEFTSHIFT'
    keys_pressed = set()
    
    context = {
        "emulator": IS_WINDOWS,
        "display": disp,
        "screen_width": width,
        "screen_height": height,
        "display_queue": display_queue,
        "run_tts": run_tts,
        "pressed_keys": keys_pressed,
        "load_icon": load_icon,
        "audio": {
            "play_sfx": play_sfx,
            "play_music": play_music,
            "stop_music": stop_music,
            "set_music_volume": set_music_volume,
        },
        "fonts": {
            "small": fontSmall,
            "default": font,
            "bold": fontBold,
            "large": fontLarge,
            "large_bold": fontLargeBold,
        },
        "apps": {
            "all": apps,
            "load": load_app_instance,
            "loaded_apps": loaded_apps,
        },
        "cursor": {
            "set_enabled": lambda enabled: display_queue.put(("set_cursor_enabled", enabled)),
            "set_app_enabled": lambda enabled: display_queue.put(("set_app_cursor_enabled", enabled)),
            "set_position": lambda x, y: display_queue.put(("set_cursor_position", x, y)),
            "clear_area": lambda: display_queue.put(("clear_cursor_area",)),
            "clear_layer": lambda: display_queue.put(("clear_base_2",)),  # Clear entire cursor layer
        },
        "get_text_size": get_text_size,
        "hash_text": hash_text,
        "FONT_PATH": FONT_PATH,
        "CACHE_DIR": CACHE_DIR,
        "APPS_DIR": APPS_DIR,
        "AUTOCOMPLETE_PATH": AUTOCOMPLETE_PATH,
    }
    
    # Create and use the reusable AppManager
    from app_manager import AppManager
    app_manager = AppManager(APPS_DIR, context)
    
    # Load all overlays
    overlay_count = app_manager.load_overlays(apps)
    print(f"[Main] Loaded {overlay_count} overlay apps")

    # Load and start the main launcher app
    if app_manager.load_app("launcher"):
        app_manager.start_app("launcher", update_rate_hz=20.0)
        print("[Main] launcher app started")
    else:
        print("[Main] Failed to load launcher app")

    # Update context to include app_manager for other apps to use
    context["app_manager"] = app_manager

    try:
        while True:
            dev = wait_for_keyboard()
            if not dev:
                display_queue.put(("set_screen", "Error", "No Keyboard Found"))
                time.sleep(5)
                continue

            display_queue.put(("set_screen", "Ready", "Waiting for input..."))
            
            try:
                for event in dev.read_loop():
                    if event.type == ecodes.EV_KEY:
                        
                        key_event = categorize(event)
                        keycode = key_event.keycode

                        if isinstance(keycode, list):
                            keycode = keycode[-1]

                        if key_event.keystate == 1: # Key down
                            if keycode in keys_pressed:
                                continue
                            
                            keys_pressed.add(keycode)
                            
                            if shift_key in keys_pressed:
                                keycode = shift_key_map.get(keycode, None)
                            app_manager.distribute_event("onkeydown", keycode)
                            
                        elif key_event.keystate == 0: # Key up
                            if keycode in keys_pressed:
                                keys_pressed.remove(keycode)
                                
                                if shift_key in keys_pressed:
                                    keycode = shift_key_map.get(keycode, None)
                                app_manager.distribute_event("onkeyup", keycode)
                            
            except OSError as e:
                if e.errno == 19:  # No such device (disconnected)
                    print("Keyboard disconnected (Errno 19). Reconnecting...", flush=True)
                    display_queue.put(("set_screen", "Disconnected", "Keyboard lost. Reconnecting..."))
                    display_queue.put(("draw_icon", searching_icon, 0, height - 8))
                    time.sleep(1)
                else:
                    raise  # Only ignore known disconnection errors
    except KeyboardInterrupt:
        print("Exiting on KeyboardInterrupt...")
    finally:
        # Stop all apps gracefully
        if 'app_manager' in locals():
            app_manager.stop_all_apps()
        
        # Clean up display
        disp.stop()  # Call our wrapper's stop method which calls cleanup()

if __name__ == "__main__":
    if not is_admin():
        print("⚠️ This script needs to be run as Administrator on Windows.")
    main()