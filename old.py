import os
import time
import hashlib
import subprocess
import threading
import math
from PIL import Image, ImageDraw, ImageFont
import queue
import select
import atexit
import bisect
import re
import platform


# --- Constants --- #

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    from config.emulator.paths import PIPER_BIN, MODEL_PATH, CACHE_DIR, APPS_DIR, ICON_DIR, FONT_PATH, AUTOCOMPLETE_PATH
else:
    from config.paths import PIPER_BIN, MODEL_PATH, CACHE_DIR, APPS_DIR, ICON_DIR, FONT_PATH, AUTOCOMPLETE_PATH

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
    import busio
    from board import SCL, SDA
    import adafruit_ssd1306

    i2c = busio.I2C(SCL, SDA)
    disp = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)

disp.fill(0)
disp.show()


# --- Application Setup --- #

apps = []

def list_apps():
    # each app is made of a folder with a main.py file inside
    for app in os.listdir(APPS_DIR):
        app_path = os.path.join(APPS_DIR, app)
        if os.path.isdir(app_path) and "main.py" in os.listdir(app_path):
            apps.append(app)

    return apps

list_apps()

print(f"Found {len(apps)} apps: {', '.join(apps)}", flush=True)

# --- Icons --- #

icons = {}

def load_icon(name, state=None):
    if state:
        img = Image.open(ICON_DIR + "/" + name + "_" + state + ".png").convert("1")
    else:
        img = Image.open(ICON_DIR + "/" + name + ".png").convert("1")
    size = img.size

    bitmap = [
        [0 if img.getpixel((x, y)) == 0 else 1 for x in range(size[0])]
        for y in range(size[1])
    ]

    icons[name] = bitmap

def create_generating_icon():
    icon = Image.new("1", (8, 8))
    d = ImageDraw.Draw(icon)
    d.line((4, 0, 4, 7), fill=255)
    d.line((0, 4, 7, 4), fill=255)
    d.line((1, 1, 6, 6), fill=255)
    d.line((1, 6, 6, 1), fill=255)
    return icon

def create_speaking_icon():
    icon = Image.new("1", (8, 8))
    d = ImageDraw.Draw(icon)
    d.polygon([(0,3), (0,4), (2,6), (2,1)], fill=255)  # speaker
    d.line((3, 2, 3, 5), fill=255)
    d.line((4, 1, 4, 6), fill=255)
    d.line((5, 0, 5, 7), fill=255)
    return icon

def create_searching_icon():
    icon = Image.new("1", (8, 8))
    d = ImageDraw.Draw(icon)
    d.ellipse((1, 1, 6, 6), outline=255, fill=0)
    d.rectangle((5, 5, 7, 7), fill=255)  # simulates a "magnifying glass"
    return icon

searching_icon = create_searching_icon()
generating_icon = create_generating_icon()
speaking_icon = create_speaking_icon()

# load the needed icons for the main menu
# load_icon("proxi")
# load_icon("notes")
# load_icon("arrhythmia")
# load_icon("config")
# load_icon("info")

# # load the needed icons for proxi
# load_icon("proxi", "generating")
# load_icon("proxi", "speaking")

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

brightness_level = 128
inverted = False

def set_display_brightness(level):
    level = max(0, min(255, level))
    disp.contrast(level)

def set_display_inverted(inverted):
    disp.invert(inverted)

width = disp.width
height = disp.height
image = Image.new("1", (width, height))
draw = ImageDraw.Draw(image)

titleLineHeight = 12
titleFontSize = 12
titlePadding = 2
bodyLineHeight = 12
bodyFontSize = 12

padding = -2
top = padding
bottom = height - padding
x = 0

titleFont = ImageFont.truetype(FONT_PATH, titleFontSize)
font = ImageFont.truetype(FONT_PATH, bodyFontSize)

draw_lock = threading.Lock()

# --- Display Functions --- #

display_queue = queue.Queue()

# To keep track of last input position for cursor blinking
lastDrawX = 0
lastDrawY = 0

def wrap_text_by_pixel_width(text, font, max_width):
    words = text.split(' ')
    lines = []
    current_line = ""

    for word in words:
        test_line = current_line + (" " if current_line else "") + word
        width = draw.textlength(test_line, font=font)
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            if draw.textlength(word, font=font) > max_width:
                partial_word = ""
                for char in word:
                    test_partial = partial_word + char
                    if draw.textlength(test_partial, font=font) <= max_width:
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

    return lines

def display_set_screen(title, text):
    global lastDrawX, lastDrawY
    with draw_lock:
        draw.rectangle((0, 0, width, height), outline=0, fill=0)
        wrapped_lines = wrap_text_by_pixel_width(text, font, width-4)
        title_width = math.ceil(draw.textlength(title, titleFont))
        title_top = top + (titleLineHeight - titleFontSize) // 2
        draw.text((x + width/2 - title_width/2, title_top), title, font=titleFont, fill=255)

        startY = top + titleLineHeight + titlePadding
        max_lines = (height - startY) // bodyLineHeight
        for i in range(min(len(wrapped_lines), max_lines)):
            draw.text((x, startY + i * bodyLineHeight), wrapped_lines[i], font=font, fill=255)
            lastDrawY = startY + i * bodyLineHeight
            lastDrawX = draw.textlength(wrapped_lines[i], font)

        disp.image(image)
        disp.show()

def display_draw_icon(icon_img, x=0, y=height - 8):
    with draw_lock:
        image.paste(icon_img, (x, y))
        disp.image(image)
        disp.show()

def display_clear_icon_area(x=0, y=height - 8):
    with draw_lock:
        draw.rectangle((x, y, x + 8, y + 8), fill=0)
        disp.image(image)
        disp.show()

def display_draw_blinking_cursor(x, y, isOn):
    with draw_lock:
        cursor_width = 2
        cursor_height = bodyLineHeight
        cursor_x = int(x) + 2
        cursor_y = int(y)
        color = 255 if isOn else 0
        draw.rectangle((cursor_x, cursor_y, cursor_x + cursor_width, cursor_y + cursor_height), fill=color)
        disp.image(image)
        disp.show()

# --- Display Thread --- #

def display_thread_func():
    is_cursor_on = False
    cursor_x = 0
    cursor_y = 0
    last_cursor_update = 0

    while True:
        # Blink cursor every 0.5 seconds
        timeout = 0.1
        try:
            cmd = display_queue.get(timeout=timeout)
        except queue.Empty:
            cmd = None

        if cmd:
            if cmd[0] == "set_screen":
                _, title, text = cmd
                display_set_screen(title, text)
            elif cmd[0] == "draw_icon":
                _, icon_img = cmd
                display_draw_icon(icon_img)
            elif cmd[0] == "clear_icon":
                display_clear_icon_area()
            elif cmd[0] == "draw_cursor":
                _, x, y, isOn = cmd
                display_draw_blinking_cursor(x, y, isOn)
            elif cmd[0] == "exit":
                break

        # Blink cursor toggle
        now = time.time()
        if now - last_cursor_update > 0.5:
            is_cursor_on = not is_cursor_on
            # Use global lastDrawX, lastDrawY for cursor position
            display_draw_blinking_cursor(lastDrawX, lastDrawY, is_cursor_on)
            last_cursor_update = now

# --- TTS + Cache --- #

os.makedirs(CACHE_DIR, exist_ok=True)

word_map = {
    'pidge': 'piddge', 'idk': 'i dont know'
}

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

def run_tts(text):
    print(f"Running TTS for: {text}", flush=True)

    if not text.strip():
        return
    
    cached_file = os.path.join(CACHE_DIR, hash_text(text) + ".raw")

    if os.path.exists(cached_file):
        print(f"Playing cached audio asynchronously for: {text}", flush=True)
        with open(cached_file, "rb") as f:
            audio_data = f.read()

        display_queue.put(("set_screen", "Cached", text))
        display_queue.put(("draw_icon", speaking_icon))
        play_thread = threading.Thread(target=play_audio_sync, args=(audio_data,))
        play_thread.start()
        play_thread.join()
        display_queue.put(("clear_icon",))

    else:
        print(f"Generating audio for: {text}", flush=True)
        display_queue.put(("set_screen", "Generating", text))
        display_queue.put(("draw_icon", generating_icon))

        try:
            mappedText = apply_word_map(text, word_map)
            raw_audio = piper_instance.synthesize(mappedText)
            display_queue.put(("clear_icon",))

            print(f"Generated audio length: {len(raw_audio)} bytes", flush=True)

            if raw_audio:
                with open(cached_file, "wb") as f:
                    f.write(raw_audio)

                display_queue.put(("set_screen", "Talking", text))
                display_queue.put(("draw_icon", speaking_icon))
                play_thread = threading.Thread(target=play_audio_sync, args=(raw_audio,))
                play_thread.start()
                play_thread.join()
                display_queue.put(("clear_icon",))
            else:
                display_queue.put(("clear_icon",))
                display_queue.put(("set_screen", "Error", "No audio generated"))
        except Exception as e:
            display_queue.put(("clear_icon",))
            print(f"Error generating or playing TTS: {e}", flush=True)
            display_queue.put(("set_screen", "Error", "TTS Generation Failed"))

# --- Input --- #

from config.keymap import key_map

def find_keyboard():
    devices = [InputDevice(path) for path in evdev.list_devices()]
    for device in devices:
        print(f"Checking device: {device.name} at {device.path}", flush=True)
        if 'mouse' in device.name.lower() or 'touchpad' in device.name.lower():
            continue
        if 'bluetooth keyboard' in device.name.lower():
            display_queue.put(("set_screen", "Connecting", f"Found Keyboard: {device.name}"))
            return device
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
        display_queue.put(("draw_icon", searching_icon))

        while tries < max_retries or max_retries == -1:
            dev = find_keyboard()
            if dev:
                display_queue.put(("clear_icon",))
                return dev

            tries += 1
            time.sleep(retry_delay)

        return None

def load_autocomplete_words(filepath):
    words = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if word:
                    words.append(word)
    except Exception as e:
        print(f"Failed to load autocomplete words from {filepath}: {e}", flush=True)
    return words

def main():
    global brightness_level
    global inverted

    set_display_brightness(brightness_level)
    set_display_inverted(inverted)

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

    # Start display thread
    disp_thread = threading.Thread(target=display_thread_func, daemon=True)
    disp_thread.start()

    currentline = ""

    shift_key = 'KEY_LEFTSHIFT'
    keys_pressed = set()

    autocomplete_words = load_autocomplete_words(AUTOCOMPLETE_PATH)
    autocomplete_words.sort()

    MIN_VOL = 60
    MAX_VOL = 100
    UI_STEPS = 20
    VOLUME_CONTROL = "Speaker"

    current_ui_volume = UI_STEPS - 5 

    def ui_to_actual_volume(ui_level):
        ratio = ui_level / UI_STEPS
        actual = int(MIN_VOL + (MAX_VOL - MIN_VOL) * ratio)
        return actual

    def set_actual_volume(percent):
        if IS_WINDOWS:
            print(f"[Volume] Skipping set to {percent}% (Windows)")
        else:
            subprocess.call(["amixer", "sset", VOLUME_CONTROL, f"{percent}%"])

    def get_autocomplete_suggestion(current_text):
        if not current_text or current_text.endswith(' '):
            return ""
        last_word = current_text.split(' ')[-1].lower()
        i = bisect.bisect_left(autocomplete_words, last_word)
        while i < len(autocomplete_words) and autocomplete_words[i].startswith(last_word):
            candidate = autocomplete_words[i]
            return candidate[len(last_word):]
        return ""
    
    actual_volume = ui_to_actual_volume(current_ui_volume)
    set_actual_volume(actual_volume)

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

                        # print(f"Key event: {keycode}", flush=True)

                        if isinstance(keycode, list):
                            keycode = keycode[-1]

                        if key_event.keystate == 1: # Key down
                            if keycode in keys_pressed:
                                continue
                            keys_pressed.add(keycode)
                        elif key_event.keystate == 0: # Key up
                            if keycode in keys_pressed:
                                keys_pressed.remove(keycode)
                            continue
                        else:
                            continue # ignore repeats

                        if shift_key in keys_pressed:
                            if keycode == 'KEY_SLASH':
                                keycode = 'KEY_QUESTION'
                            elif keycode == 'KEY_BACKSLASH':
                                keycode = 'KEY_PIPE'
                            elif keycode == 'KEY_GRAVE':
                                keycode = 'KEY_TILDE'

                        if keycode == 'KEY_BRIGHTNESSUP':
                            brightness_level = min(brightness_level + 32, 255)
                            set_display_brightness(brightness_level)
                            display_queue.put(("set_screen", "Brightness", f"Up: {brightness_level}"))
                            continue
                        elif keycode == 'KEY_BRIGHTNESSDOWN':
                            brightness_level = max(brightness_level - 32, 0)
                            set_display_brightness(brightness_level)
                            display_queue.put(("set_screen", "Brightness", f"Down: {brightness_level}"))
                            continue

                        elif keycode == 'KEY_HOMEPAGE':
                            inverted = not inverted
                            set_display_inverted(inverted)
                            display_queue.put(("set_screen", "Inverted", f"{inverted}"))
                            continue

                        elif keycode == 'KEY_VOLUMEUP':
                            current_ui_volume = min(current_ui_volume + 1, UI_STEPS)
                            actual_volume = ui_to_actual_volume(current_ui_volume)
                            set_actual_volume(actual_volume)
                            display_queue.put(("set_screen", "Volume", f"Up: {round(current_ui_volume / UI_STEPS * 100)}%"))
                            continue
                        elif keycode == 'KEY_VOLUMEDOWN':
                            current_ui_volume = max(current_ui_volume - 1, 0)
                            actual_volume = ui_to_actual_volume(current_ui_volume)
                            set_actual_volume(actual_volume)
                            display_queue.put(("set_screen", "Volume", f"Down: {round(current_ui_volume / UI_STEPS * 100)}%"))
                            continue

                        # auto complete
                        elif keycode == 'KEY_TAB' or (shift_key in keys_pressed and keycode == 'KEY_SPACE'):
                            suggestion = get_autocomplete_suggestion(currentline)
                            if suggestion:
                                currentline += suggestion
                            display_queue.put(("set_screen", "Input", currentline))
                            continue

                        char = key_map.get(keycode, None)
                        if char is None:
                            continue

                        if keycode == 'KEY_ENTER':
                            old_line = currentline
                            run_tts(currentline)
                            cached_path = os.path.join(CACHE_DIR, hash_text(old_line) + ".raw")
                            if os.path.exists(cached_path):
                                currentline = ""
                                display_queue.put(("set_screen", "Ready", "Waiting for input..."))
                            else:
                                display_queue.put(("set_screen", "Input", old_line))
                        elif keycode == 'KEY_BACKSPACE':
                            currentline = currentline[:-1]
                            display_queue.put(("set_screen", "Input", currentline))
                        else:
                            currentline += char
                            suggestion = get_autocomplete_suggestion(currentline)
                            if not suggestion:
                                display_queue.put(("set_screen", "Input", currentline))
                            else:
                                display_queue.put(("set_screen", "Input", currentline + "|" + suggestion))
            except OSError as e:
                if e.errno == 19:  # No such device (disconnected)
                    print("Keyboard disconnected (Errno 19). Reconnecting...", flush=True)
                    display_queue.put(("set_screen", "Disconnected", "Keyboard lost. Reconnecting..."))
                    display_queue.put(("draw_icon", searching_icon))
                    time.sleep(1)
                else:
                    raise  # Only ignore known disconnection errors
    except KeyboardInterrupt:
        print("Exiting on KeyboardInterrupt...")
    finally:
        # Clean up display on Windows
        if IS_WINDOWS:
            disp.stop()


if __name__ == "__main__":
    if not is_admin():
        print("⚠️ This script needs to be run as Administrator on Windows.")

    main()