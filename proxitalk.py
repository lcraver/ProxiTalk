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
import requests
import json
import io
import wave
from PIL import Image, ImageDraw, ImageFont

# --- Constants --- #

IS_WINDOWS = platform.system() == "Windows"

# I2C settings for luma.oled (Linux only)
I2C_PORT = 1        # I2C port (usually 1 on Raspberry Pi)
I2C_ADDRESS = 0x3C  # Common I2C address for SSD1306 displays

if IS_WINDOWS:
    from config.emulator.paths import PIPER_BIN, MODEL_PATH, VOICEVOX_BIN, VOICEVOX_HOST, VOICEVOX_PORT, CACHE_DIR, CONFIG_DIR, APPS_DIR, ICON_DIR, AUTOCOMPLETE_PATH
    from config.emulator.paths import FONT_PATH, FONT_SMALL_PATH, OVERLAY_DIR
else:
    from config.paths import PIPER_BIN, MODEL_PATH, VOICEVOX_BIN, VOICEVOX_HOST, VOICEVOX_PORT, CACHE_DIR, CONFIG_DIR, APPS_DIR, ICON_DIR, AUTOCOMPLETE_PATH
    from config.paths import FONT_PATH, FONT_SMALL_PATH, OVERLAY_DIR
    
# -- Emulator Setup --- #

def is_admin():
    if not IS_WINDOWS:
        return True  # Assume admin on non-Windows
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

import pygame
import threading
import io
import wave

if IS_WINDOWS:
    # use the keyboard module or mock input
    import keyboard
else:
    import evdev
    from evdev import InputDevice, categorize, ecodes

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

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
            
            # Debug overlay for region updates
            self._debug_regions = []
            self._debug_overlay_duration = 1/20 * 5  # Show overlay for 5 frames at 20 FPS
            self._show_debug_overlay = True  # Toggle this to enable/disable debug overlay
            
            # Window focus tracking
            self._window_focused = True
            self._focus_check_timer = 0

            self._thread = threading.Thread(target=self._run_pygame_loop, daemon=True)
            self._thread.start()
        
        def is_window_focused(self):
            """Check if the pygame window is currently focused using Windows API"""
            if not IS_WINDOWS:
                return self._window_focused
                
            try:
                # Get the currently active window
                foreground_window = ctypes.windll.user32.GetForegroundWindow()
                
                # Check if any window with our title is active
                window_title = "ProxiTalk Emulated Display"
                title_buffer = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(foreground_window, title_buffer, 256)
                active_title = title_buffer.value
                
                return active_title == window_title
                
            except Exception as e:
                print(f"[Focus] Error checking window focus: {e}")
                return self._window_focused

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
        
        def add_debug_region(self, x, y, width, height):
            """Add a debug region to visualize updates"""
            if self._show_debug_overlay:
                import time
                with self._update_lock:
                    self._debug_regions.append({
                        'x': x, 'y': y, 'width': width, 'height': height,
                        'timestamp': time.time()
                    })

        def _run_pygame_loop(self):
            import time  # Import time module for timestamp calculations
            try:
                pygame.init()
                self.screen = pygame.display.set_mode((self.width * self.scale, self.height * self.scale))
                pygame.display.set_caption("ProxiTalk Emulated Display")
                clock = pygame.time.Clock()
                last_surface = None  # Keep track of the last displayed surface
                
                print("[Display] Pygame display initialized successfully")
                
            except Exception as e:
                print(f"[Error] Failed to initialize pygame display: {e}")
                self._stop_event.set()
                return

            try:
                while not self._stop_event.is_set():
                    try:
                        for event in pygame.event.get():
                            if event.type == pygame.QUIT:
                                print("[Display] Received QUIT event")
                                self._stop_event.set()
                            elif event.type == pygame.KEYDOWN:
                                # Toggle debug overlay with F1 key
                                if event.key == pygame.K_F1:
                                    self._show_debug_overlay = not self._show_debug_overlay
                                    print(f"[Debug] Region overlay: {'ON' if self._show_debug_overlay else 'OFF'}")
                    except Exception as e:
                        print(f"[Error] Exception in pygame event handling: {e}")
                        continue

                    current_time = time.time()
                    
                    # Check window focus periodically using Windows API instead of pygame events
                    if current_time - self._focus_check_timer > 0.5:  # Check every 500ms
                        old_focus_state = self._window_focused
                        if IS_WINDOWS:
                            try:
                                # Get the currently active window
                                foreground_window = ctypes.windll.user32.GetForegroundWindow()
                                
                                # Check if any window with our title is active
                                window_title = "ProxiTalk Emulated Display"
                                title_buffer = ctypes.create_unicode_buffer(256)
                                ctypes.windll.user32.GetWindowTextW(foreground_window, title_buffer, 256)
                                active_title = title_buffer.value
                                self._window_focused = (active_title == window_title)
                                
                                # Log focus changes
                                if old_focus_state != self._window_focused:
                                    print(f"[Focus] Window focus changed: {self._window_focused}")
                                    
                            except Exception as e:
                                print(f"[Focus] Error checking window focus: {e}")
                        
                        self._focus_check_timer = current_time
                    
                    needs_redraw = False
                
                    with self._update_lock:
                        # Check if we have a new image to display
                        if self._pending_image:
                            img = self._pending_image
                            size = img.size

                            # Convert to RGB for pygame compatibility
                            img_rgb = img.convert("RGB")
                            data = img_rgb.tobytes()
                            last_surface = pygame.image.fromstring(data, size, "RGB")
                            last_surface = pygame.transform.scale(last_surface, (self.width * self.scale, self.height * self.scale))
                            needs_redraw = True
                            self._pending_image = None
                        
                        # Always process debug overlay if enabled, even without new image
                        if self._show_debug_overlay:
                            # Remove expired debug regions
                            old_region_count = len(self._debug_regions)
                            self._debug_regions = [
                                region for region in self._debug_regions 
                                if current_time - region['timestamp'] < self._debug_overlay_duration
                            ]
                            # If regions were removed or still exist, we need to redraw
                            if old_region_count != len(self._debug_regions) or self._debug_regions:
                                needs_redraw = True
                    
                    # Redraw if we have changes or active debug regions
                    if needs_redraw and last_surface:
                        self.screen.blit(last_surface, (0, 0))
                        
                        # Draw debug overlay for region updates
                        if self._show_debug_overlay:
                            for region in self._debug_regions:
                                # Calculate fade based on age
                                age = current_time - region['timestamp']
                                alpha = max(0, min(255, int(255 * (1.0 - age / self._debug_overlay_duration))))
                                
                                if alpha > 0:
                                    # Create a red transparent surface
                                    overlay = pygame.Surface((region['width'] * self.scale, region['height'] * self.scale))
                                    overlay.set_alpha(alpha // 2)  # Make it semi-transparent
                                    overlay.fill((255, 0, 0))  # Red color
                                    
                                    # Blit the overlay
                                    self.screen.blit(overlay, (region['x'] * self.scale, region['y'] * self.scale))
                        
                        pygame.display.flip()

                    clock.tick(12)  # Limit to 12 FPS
                    
            except Exception as e:
                print(f"[Error] Critical error in pygame main loop: {e}")
                self._stop_event.set()
            finally:
                print("[Display] Pygame loop ended")

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

class AudioStreamer:
    def __init__(self):
        self.is_streaming = False
        self.stream_thread = None
        self._stop_event = threading.Event()
        self.current_audio_file = None
        self.start_time = 0
        self.pause_time = 0
        self.is_paused = False
        self.volume = 0.7
        
    def start_stream(self, audio_file_path: str, start_offset: float = 0.0):
        """Start streaming audio from a file with optional offset"""
        if not os.path.isfile(audio_file_path):
            print(f"[AudioStream] File not found: {audio_file_path}", flush=True)
            return False
        
        # Check if pygame mixer is initialized
        try:
            mixer_info = pygame.mixer.get_init()
            if mixer_info is None:
                print(f"[AudioStream] Pygame mixer not initialized, initializing...", flush=True)
                pygame.mixer.init(frequency=22050, size=-16, channels=1)
                mixer_info = pygame.mixer.get_init()
            
            print(f"[AudioStream] Pygame mixer settings: {mixer_info}", flush=True)
        except Exception as e:
            print(f"[AudioStream] Error checking pygame mixer: {e}", flush=True)
            return False
        
        print(f"[AudioStream] Starting stream for: {audio_file_path}", flush=True)
        
        self.stop_stream()
        self._stop_event.clear()
        self.current_audio_file = audio_file_path
        self.is_streaming = True
        self.is_paused = False
        self.start_time = time.time() - start_offset
        self.pause_time = 0
        
        try:
            self.stream_thread = threading.Thread(
                target=self._stream_audio_loop, 
                args=(audio_file_path, start_offset), 
                daemon=True
            )
            self.stream_thread.start()
            print(f"[AudioStream] Stream thread started", flush=True)
            return True
        except Exception as e:
            print(f"[AudioStream] Error starting stream thread: {e}", flush=True)
            self.is_streaming = False
            return False
    
    def _stream_audio_loop(self, audio_file_path: str, start_offset: float):
        """Internal method to handle audio streaming"""
        try:
            print(f"[AudioStream] Loading audio file: {audio_file_path}", flush=True)
            
            # Load the entire audio file
            sound = pygame.mixer.Sound(audio_file_path)
            sound.set_volume(self.volume)
            
            print(f"[AudioStream] Starting playback (offset: {start_offset}s)", flush=True)
            
            # Start playback - pygame doesn't support start offset directly
            # For now, we'll play from the beginning
            channel = sound.play()
            
            if not channel:
                print("[AudioStream] Failed to get audio channel", flush=True)
                return
            
            print("[AudioStream] Audio playback started successfully", flush=True)
            
            # Monitor playback and handle pause/resume
            while channel.get_busy() and not self._stop_event.is_set() and self.is_streaming:
                if self.is_paused:
                    channel.pause()
                    print("[AudioStream] Channel paused", flush=True)
                    # Wait while paused
                    while self.is_paused and not self._stop_event.is_set():
                        time.sleep(0.1)
                    if not self._stop_event.is_set() and self.is_streaming:
                        channel.unpause()
                        print("[AudioStream] Channel unpaused", flush=True)
                
                pygame.time.wait(100)
            
            print("[AudioStream] Audio playback finished", flush=True)
            
        except pygame.error as e:
            print(f"[AudioStream] Pygame error streaming audio '{audio_file_path}': {e}", flush=True)
        except Exception as e:
            print(f"[AudioStream] Error streaming audio '{audio_file_path}': {e}", flush=True)
        finally:
            self.is_streaming = False
            self.is_paused = False
    
    def pause_stream(self):
        """Pause the current audio stream"""
        if self.is_streaming and not self.is_paused:
            self.is_paused = True
            self.pause_time = time.time()
            print("[AudioStream] Audio paused", flush=True)
    
    def resume_stream(self):
        """Resume the paused audio stream"""
        if self.is_streaming and self.is_paused:
            self.is_paused = False
            # Adjust start time to account for pause duration
            if self.pause_time > 0:
                pause_duration = time.time() - self.pause_time
                self.start_time += pause_duration
            print("[AudioStream] Audio resumed", flush=True)
    
    def stop_stream(self):
        """Stop the current audio stream"""
        self.is_streaming = False
        self.is_paused = False
        self._stop_event.set()
        
        # Stop all pygame channels
        pygame.mixer.stop()
        
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=1.0)
        
        self.current_audio_file = None
        self.start_time = 0
        self.pause_time = 0
        print("[AudioStream] Audio stream stopped", flush=True)
    
    def set_stream_volume(self, volume: float):
        """Set the streaming audio volume (0.0 to 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
        print(f"[AudioStream] Volume set to {self.volume:.2f}", flush=True)
    
    def get_current_position(self) -> float:
        """Get the current playback position in seconds"""
        if not self.is_streaming:
            return 0.0
        
        if self.is_paused and self.pause_time > 0:
            return self.pause_time - self.start_time
        else:
            return time.time() - self.start_time
    
    def is_stream_playing(self) -> bool:
        """Check if audio is currently streaming"""
        return self.is_streaming and not self.is_paused
    
    def is_stream_paused(self) -> bool:
        """Check if audio stream is paused"""
        return self.is_streaming and self.is_paused
    
    def get_stream_info(self) -> dict:
        """Get information about the current stream"""
        return {
            "file": self.current_audio_file,
            "is_playing": self.is_stream_playing(),
            "is_paused": self.is_stream_paused(),
            "current_position": self.get_current_position(),
            "volume": self.volume
        }

# Global audio streamer
audio_streamer = AudioStreamer()

def start_audio_stream(audio_file_path: str, start_offset: float = 0.0):
    """Start streaming audio from a file"""
    return audio_streamer.start_stream(audio_file_path, start_offset)

def pause_audio_stream():
    """Pause the current audio stream"""
    audio_streamer.pause_stream()

def resume_audio_stream():
    """Resume the paused audio stream"""
    audio_streamer.resume_stream()

def stop_audio_stream():
    """Stop the current audio stream"""
    audio_streamer.stop_stream()

def set_audio_stream_volume(volume: float):
    """Set the streaming audio volume"""
    audio_streamer.set_stream_volume(volume)

def get_audio_stream_position() -> float:
    """Get current playback position in seconds"""
    return audio_streamer.get_current_position()

def is_audio_stream_playing() -> bool:
    """Check if audio stream is playing"""
    return audio_streamer.is_stream_playing()

def is_audio_stream_paused() -> bool:
    """Check if audio stream is paused"""
    return audio_streamer.is_stream_paused()

def get_audio_stream_info() -> dict:
    """Get information about current audio stream"""
    return audio_streamer.get_stream_info()

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
                max_wait = 6.0

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

# --- VoiceVox TTS --- #

if IS_WINDOWS:
    class PersistentVoiceVox:
        def __init__(self, voicevox_bin, host, port, speaker_id=2):
            self.voicevox_bin = voicevox_bin
            self.host = host
            self.port = port
            self.speaker_id = speaker_id
            self.base_url = f"http://{host}:{port}"
            self.process = None
            self.lock = threading.Lock()
            self.is_running = False
            self.start_process()

        def start_process(self):
            """Start VoiceVox engine process"""
            try:
                print(f"[VoiceVox] Starting VoiceVox engine: {self.voicevox_bin}")
                self.process = subprocess.Popen(
                    [self.voicevox_bin],
                    creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
                )
                # Wait a moment for the server to start
                time.sleep(3)
                self.is_running = self._check_server_status()
                if self.is_running:
                    print(f"[VoiceVox] Engine started successfully at {self.base_url}")
                else:
                    print(f"[VoiceVox] Failed to start engine or server not responding")
            except Exception as e:
                print(f"[VoiceVox] Failed to start engine: {e}")
                self.is_running = False

        def _check_server_status(self):
            """Check if VoiceVox server is responding"""
            try:
                response = requests.get(f"{self.base_url}/version", timeout=2)
                return response.status_code == 200
            except:
                return False

        def synthesize(self, text, timeout=10.0):
            """Synthesize text to audio using VoiceVox API"""
            with self.lock:
                if not self.is_running or not self._check_server_status():
                    print("[VoiceVox] Server not running. Restarting.", flush=True)
                    self.start_process()
                    if not self.is_running:
                        return b''

                try:
                    # Step 1: Create audio query
                    query_response = requests.post(
                        f"{self.base_url}/audio_query",
                        params={"text": text, "speaker": self.speaker_id},
                        timeout=timeout
                    )
                    if query_response.status_code != 200:
                        print(f"[VoiceVox] Audio query failed: {query_response.status_code}")
                        return b''
                    
                    audio_query = query_response.json()
                    
                    # Step 2: Synthesize audio
                    synthesis_response = requests.post(
                        f"{self.base_url}/synthesis",
                        headers={"Content-Type": "application/json"},
                        params={"speaker": self.speaker_id},
                        data=json.dumps(audio_query),
                        timeout=timeout
                    )
                    
                    if synthesis_response.status_code != 200:
                        print(f"[VoiceVox] Synthesis failed: {synthesis_response.status_code}")
                        return b''
                    
                    return synthesis_response.content
                    
                except requests.exceptions.RequestException as e:
                    print(f"[VoiceVox] Request error: {e}")
                    return b''
                except Exception as e:
                    print(f"[VoiceVox] Synthesis error: {e}")
                    return b''

        def set_speaker_id(self, speaker_id):
            """Change the speaker ID"""
            self.speaker_id = speaker_id
            print(f"[VoiceVox] Speaker ID changed to: {speaker_id}")

        def get_speakers(self):
            """Get available speakers from VoiceVox API"""
            try:
                if not self.is_running or not self._check_server_status():
                    print("[VoiceVox] Server not running, cannot get speakers")
                    return []
                
                response = requests.get(f"{self.base_url}/speakers", timeout=5)
                if response.status_code == 200:
                    speakers_data = response.json()
                    speakers = []
                    for speaker in speakers_data:
                        name = speaker.get('name', 'Unknown')
                        speaker_uuid = speaker.get('speaker_uuid', '')
                        version = speaker.get('version', '')
                        
                        # Create a voice entry for this speaker
                        voice_info = {
                            'name': name,
                            'uuid': speaker_uuid,
                            'version': version,
                            'styles': []
                        }
                        
                        # Add all styles for this voice
                        for style in speaker.get('styles', []):
                            style_info = {
                                'id': style.get('id', 0),
                                'name': style.get('name', 'Normal'),
                                'type': style.get('type', 'talk')
                            }
                            voice_info['styles'].append(style_info)
                        
                        speakers.append(voice_info)
                    
                    return speakers
                else:
                    print(f"[VoiceVox] Failed to get speakers: {response.status_code}")
                    return []
            except Exception as e:
                print(f"[VoiceVox] Error getting speakers: {e}")
                return []

        def close(self):
            """Cleanup VoiceVox process"""
            self.is_running = False
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3)
                except Exception as e:
                    print(f"[VoiceVox] Cleanup error: {e}")
else:
    class PersistentVoiceVox:
        def __init__(self, voicevox_bin, host, port, speaker_id=2):
            self.voicevox_bin = voicevox_bin
            self.host = host
            self.port = port
            self.speaker_id = speaker_id
            self.base_url = f"http://{host}:{port}"
            self.process = None
            self.lock = threading.Lock()
            self.is_running = False
            self.start_process()

        def start_process(self):
            """Start VoiceVox engine process"""
            try:
                print(f"[VoiceVox] Starting VoiceVox engine: {self.voicevox_bin}")
                self.process = subprocess.Popen([self.voicevox_bin])
                # Wait a moment for the server to start
                time.sleep(3)
                self.is_running = self._check_server_status()
                if self.is_running:
                    print(f"[VoiceVox] Engine started successfully at {self.base_url}")
                else:
                    print(f"[VoiceVox] Failed to start engine or server not responding")
            except Exception as e:
                print(f"[VoiceVox] Failed to start engine: {e}")
                self.is_running = False

        def _check_server_status(self):
            """Check if VoiceVox server is responding"""
            try:
                response = requests.get(f"{self.base_url}/version", timeout=2)
                return response.status_code == 200
            except:
                return False

        def synthesize(self, text, timeout=10.0):
            """Synthesize text to audio using VoiceVox API"""
            with self.lock:
                if not self.is_running or not self._check_server_status():
                    print("[VoiceVox] Server not running. Restarting.", flush=True)
                    self.start_process()
                    if not self.is_running:
                        return b''

                try:
                    # Step 1: Create audio query
                    query_response = requests.post(
                        f"{self.base_url}/audio_query",
                        params={"text": text, "speaker": self.speaker_id},
                        timeout=timeout
                    )
                    if query_response.status_code != 200:
                        print(f"[VoiceVox] Audio query failed: {query_response.status_code}")
                        return b''
                    
                    audio_query = query_response.json()
                    
                    # Step 2: Synthesize audio
                    synthesis_response = requests.post(
                        f"{self.base_url}/synthesis",
                        headers={"Content-Type": "application/json"},
                        params={"speaker": self.speaker_id},
                        data=json.dumps(audio_query),
                        timeout=timeout
                    )
                    
                    if synthesis_response.status_code != 200:
                        print(f"[VoiceVox] Synthesis failed: {synthesis_response.status_code}")
                        return b''
                    
                    return synthesis_response.content
                    
                except requests.exceptions.RequestException as e:
                    print(f"[VoiceVox] Request error: {e}")
                    return b''
                except Exception as e:
                    print(f"[VoiceVox] Synthesis error: {e}")
                    return b''

        def set_speaker_id(self, speaker_id):
            """Change the speaker ID"""
            self.speaker_id = speaker_id
            print(f"[VoiceVox] Speaker ID changed to: {speaker_id}")

        def get_speakers(self):
            """Get available speakers from VoiceVox API"""
            try:
                if not self.is_running or not self._check_server_status():
                    print("[VoiceVox] Server not running, cannot get speakers")
                    return []
                
                response = requests.get(f"{self.base_url}/speakers", timeout=5)
                if response.status_code == 200:
                    speakers_data = response.json()
                    speakers = []
                    for speaker in speakers_data:
                        name = speaker.get('name', 'Unknown')
                        speaker_uuid = speaker.get('speaker_uuid', '')
                        version = speaker.get('version', '')
                        
                        # Create a voice entry for this speaker
                        voice_info = {
                            'name': name,
                            'uuid': speaker_uuid,
                            'version': version,
                            'styles': []
                        }
                        
                        # Add all styles for this voice
                        for style in speaker.get('styles', []):
                            style_info = {
                                'id': style.get('id', 0),
                                'name': style.get('name', 'Normal'),
                                'type': style.get('type', 'talk')
                            }
                            voice_info['styles'].append(style_info)
                        
                        speakers.append(voice_info)
                    
                    return speakers
                else:
                    print(f"[VoiceVox] Failed to get speakers: {response.status_code}")
                    return []
            except Exception as e:
                print(f"[VoiceVox] Error getting speakers: {e}")
                return []

        def close(self):
            """Cleanup VoiceVox process"""
            self.is_running = False
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3)
                except Exception as e:
                    print(f"[VoiceVox] Cleanup error: {e}")

# --- TTS Engine Manager --- #

class TTSEngineManager:
    def __init__(self, piper_bin, model_path, voicevox_bin, voicevox_host, voicevox_port):
        self.piper_instance = None
        self.voicevox_instance = None
        self.current_engine = "piper"  # Default to Piper
        self.piper_bin = piper_bin
        self.model_path = model_path
        self.voicevox_bin = voicevox_bin
        self.voicevox_host = voicevox_host
        self.voicevox_port = voicevox_port
        
        # VoiceVox speaker caching
        self._voicevox_speakers_cache = None
        self._voicevox_speakers_flat_cache = None
        self._cache_timestamp = None
        self._cache_duration = 300  # Cache for 5 minutes
        
        # Initialize Piper by default
        self._init_piper()
        
        # Preload VoiceVox speakers in background
        self._preload_voicevox_speakers()
    
    def _preload_voicevox_speakers(self):
        """Preload VoiceVox speakers in a background thread"""
        def preload_thread():
            try:
                print("[TTS] Starting VoiceVox speaker preloading...")
                # Give VoiceVox a moment to start if it's initializing
                time.sleep(1)
                
                # Initialize VoiceVox if needed
                if not self.voicevox_instance:
                    print("[TTS] Initializing VoiceVox for preloading...")
                    self._init_voicevox()
                
                # Load speakers into cache
                if self.voicevox_instance:
                    print("[TTS] Fetching speakers from VoiceVox API...")
                    speakers = self.voicevox_instance.get_speakers()
                    if speakers:
                        self._update_speaker_cache(speakers)
                        print(f"[TTS] Successfully preloaded {len(speakers)} VoiceVox voices")
                        
                        # Log some details about what was cached
                        total_styles = sum(len(voice['styles']) for voice in speakers)
                        print(f"[TTS] Cached {total_styles} total styles across all voices")
                    else:
                        print("[TTS] No VoiceVox speakers available for preloading (empty response)")
                else:
                    print("[TTS] VoiceVox instance not available for preloading")
            except Exception as e:
                print(f"[TTS] Error during VoiceVox speaker preloading: {e}")
                import traceback
                traceback.print_exc()
        
        # Start preloading in background thread
        threading.Thread(target=preload_thread, daemon=True).start()
    
    def _update_speaker_cache(self, speakers):
        """Update the speaker cache with new data"""
        self._voicevox_speakers_cache = speakers
        self._cache_timestamp = time.time()
        
        # Generate flat cache
        flat_list = []
        for voice in speakers:
            voice_name = voice['name']
            for style in voice['styles']:
                flat_list.append({
                    'id': style['id'],
                    'name': f"{voice_name} ({style['name']})",
                    'voice': voice_name,
                    'style': style['name'],
                    'type': style['type']
                })
        self._voicevox_speakers_flat_cache = flat_list
    
    def _is_cache_valid(self):
        """Check if the speaker cache is still valid"""
        if self._cache_timestamp is None:
            return False
        return (time.time() - self._cache_timestamp) < self._cache_duration
    
    def _refresh_speaker_cache(self):
        """Refresh the speaker cache if needed"""
        if not self._is_cache_valid():
            print("[TTS] Speaker cache expired, refreshing...")
            if self.voicevox_instance:
                speakers = self.voicevox_instance.get_speakers()
                if speakers:
                    self._update_speaker_cache(speakers)
                    return True
        return self._voicevox_speakers_cache is not None
    
    def _init_piper(self):
        """Initialize Piper TTS engine"""
        try:
            if self.piper_instance:
                self.piper_instance.close()
            self.piper_instance = PersistentPiper(self.piper_bin, self.model_path)
            print("[TTS] Piper engine initialized")
        except Exception as e:
            print(f"[TTS] Failed to initialize Piper: {e}")
    
    def _init_voicevox(self):
        """Initialize VoiceVox TTS engine"""
        try:
            if self.voicevox_instance:
                self.voicevox_instance.close()
            
            # Get speaker ID from user preferences
            from config.user_preferences import user_preferences
            speaker_id = 2  # Default
            if user_preferences:
                speaker_id = user_preferences.get_voicevox_speaker_id()
            
            self.voicevox_instance = PersistentVoiceVox(
                self.voicevox_bin, self.voicevox_host, self.voicevox_port, speaker_id
            )
            print("[TTS] VoiceVox engine initialized")
        except Exception as e:
            print(f"[TTS] Failed to initialize VoiceVox: {e}")
    
    def set_engine(self, engine_name):
        """Switch between TTS engines"""
        if engine_name not in ["piper", "voicevox"]:
            print(f"[TTS] Invalid engine name: {engine_name}")
            return False
        
        if engine_name == self.current_engine:
            print(f"[TTS] Already using {engine_name} engine")
            return True
        
        print(f"[TTS] Switching from {self.current_engine} to {engine_name}")
        self.current_engine = engine_name
        
        if engine_name == "voicevox" and not self.voicevox_instance:
            self._init_voicevox()
        elif engine_name == "piper" and not self.piper_instance:
            self._init_piper()
        
        return True
    
    def synthesize(self, text, background=False):
        """Synthesize text using the current engine"""
        if self.current_engine == "piper" and self.piper_instance:
            if IS_WINDOWS:
                return self.piper_instance.synthesize(text, timeout=5.0)
            else:
                return self.piper_instance.synthesize(text)
        elif self.current_engine == "voicevox" and self.voicevox_instance:
            return self.voicevox_instance.synthesize(text, timeout=10.0)
        else:
            print(f"[TTS] No active {self.current_engine} engine instance")
            return b''
    
    def set_voicevox_speaker(self, speaker_id):
        """Set VoiceVox speaker ID"""
        if self.voicevox_instance:
            self.voicevox_instance.set_speaker_id(speaker_id)
            # Save to preferences
            from config.user_preferences import user_preferences
            if user_preferences:
                user_preferences.set_voicevox_speaker_id(speaker_id)
        else:
            print("[TTS] VoiceVox not initialized")
    
    def get_voicevox_speakers(self):
        """Get available VoiceVox speakers (cached)"""
        # Try to use cache first
        if self._is_cache_valid() and self._voicevox_speakers_cache:
            return self._voicevox_speakers_cache
        
        # Cache miss or expired, try to refresh
        if self._refresh_speaker_cache():
            return self._voicevox_speakers_cache
        
        # Fallback to direct API call if cache refresh fails
        if not self.voicevox_instance:
            self._init_voicevox()
        
        if self.voicevox_instance:
            speakers = self.voicevox_instance.get_speakers()
            if speakers:
                self._update_speaker_cache(speakers)
                return speakers
        
        return []
    
    def get_voicevox_speakers_flat(self):
        """Get VoiceVox speakers as a flat list for UI compatibility (cached)"""
        # Try to use cache first
        if self._is_cache_valid() and self._voicevox_speakers_flat_cache:
            return self._voicevox_speakers_flat_cache
        
        # Cache miss or expired, refresh using main method
        voices = self.get_voicevox_speakers()
        if self._voicevox_speakers_flat_cache:
            return self._voicevox_speakers_flat_cache
        
        # Fallback generation if cache is empty
        flat_list = []
        for voice in voices:
            voice_name = voice['name']
            for style in voice['styles']:
                flat_list.append({
                    'id': style['id'],
                    'name': f"{voice_name} ({style['name']})",
                    'voice': voice_name,
                    'style': style['name'],
                    'type': style['type']
                })
        
        return flat_list
    
    def refresh_voicevox_speakers_cache(self):
        """Force refresh the VoiceVox speakers cache"""
        print("[TTS] Force refreshing VoiceVox speakers cache...")
        self._cache_timestamp = None  # Invalidate cache
        if not self.voicevox_instance:
            self._init_voicevox()
        
        if self.voicevox_instance:
            speakers = self.voicevox_instance.get_speakers()
            if speakers:
                self._update_speaker_cache(speakers)
                print(f"[TTS] Cache refreshed with {len(speakers)} voices")
                return True
        
        print("[TTS] Failed to refresh VoiceVox speakers cache")
        return False
    
    def get_current_engine(self):
        """Get the name of the current TTS engine"""
        return self.current_engine
    
    def close_all(self):
        """Close all TTS engines"""
        if self.piper_instance:
            self.piper_instance.close()
        if self.voicevox_instance:
            self.voicevox_instance.close()

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
        (FONT_SMALL_PATH, "Small font file")
    ]
    
    for path, name in required_fonts:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{name} not found: {path}")

load_fonts()

fontSmall = ImageFont.truetype(FONT_SMALL_PATH, 4)
font = ImageFont.truetype(FONT_PATH, 11)
fontLarge = ImageFont.truetype(FONT_PATH, 24)

# --- Render composite display --- #
# Track if display needs updating to avoid unnecessary redraws
display_dirty = True
# Track dirty regions for partial updates
dirty_regions = []

class DirtyRegion:
    def __init__(self, x, y, width, height):
        self.x = max(0, min(x, 128))  # Screen width is 128
        self.y = max(0, min(y, 64))   # Screen height is 64
        self.width = max(0, min(width, 128 - self.x))
        self.height = max(0, min(height, 64 - self.y))
    
    def intersects(self, other):
        """Check if this region intersects with another"""
        return not (self.x + self.width <= other.x or 
                   other.x + other.width <= self.x or
                   self.y + self.height <= other.y or 
                   other.y + other.height <= self.y)
    
    def merge(self, other):
        """Merge this region with another, returning a new region"""
        left = min(self.x, other.x)
        top = min(self.y, other.y) 
        right = max(self.x + self.width, other.x + other.width)
        bottom = max(self.y + self.height, other.y + other.height)
        return DirtyRegion(left, top, right - left, bottom - top)

def add_dirty_region(x, y, width, height):
    """Add a dirty region, merging with overlapping regions"""
    global dirty_regions
    new_region = DirtyRegion(x, y, width, height)
    
    # Find overlapping regions and merge them
    merged_regions = []
    for region in dirty_regions:
        if new_region.intersects(region):
            new_region = new_region.merge(region)
        else:
            merged_regions.append(region)
    
    merged_regions.append(new_region)
    dirty_regions = merged_regions

def update_display(force=False, region=None):
    """Update display with optional region-based updates"""
    global display_dirty, dirty_regions
    
    if region:
        # Add specific region to dirty list
        add_dirty_region(region[0], region[1], region[2], region[3])
    
    if not display_dirty and not dirty_regions and not force:
        return
        
    with draw_lock:
        if force or not dirty_regions:
            # Full screen update
            composite_layer.paste(base_layer)
            composite_layer.paste(base_layer_2, (0, 0), base_layer_2)
            composite_layer.paste(overlay_layer, (0, 0), overlay_layer)
            disp.image(composite_layer)
            disp.show()
            
            # Add debug region for full screen update (Windows only)
            if IS_WINDOWS and hasattr(disp, 'add_debug_region'):
                disp.add_debug_region(0, 0, width, height)
            
            dirty_regions = []
        else:
            # Update only dirty regions
            for region in dirty_regions:
                # Extract region from each layer
                base_region = base_layer.crop((region.x, region.y, 
                                             region.x + region.width, 
                                             region.y + region.height))
                base2_region = base_layer_2.crop((region.x, region.y,
                                                region.x + region.width,
                                                region.y + region.height))
                overlay_region = overlay_layer.crop((region.x, region.y,
                                                   region.x + region.width,
                                                   region.y + region.height))
                
                # Composite the region
                temp_region = Image.new("1", (region.width, region.height))
                temp_region.paste(base_region)
                temp_region.paste(base2_region, (0, 0), base2_region)
                temp_region.paste(overlay_region, (0, 0), overlay_region)
                
                # Paste back to composite layer
                composite_layer.paste(temp_region, (region.x, region.y))
                
                # Add debug region visualization (Windows only)
                if IS_WINDOWS and hasattr(disp, 'add_debug_region'):
                    disp.add_debug_region(region.x, region.y, region.width, region.height)
            
            # Send full composite to display (hardware limitation)
            disp.image(composite_layer)
            disp.show()
            dirty_regions = []
        
        display_dirty = False

def mark_display_dirty(x=None, y=None, width=None, height=None):
    """Mark display as dirty, optionally with specific region"""
    global display_dirty
    display_dirty = True
    if x is not None and y is not None and width is not None and height is not None:
        add_dirty_region(x, y, width, height)

# --- Display Functions (modified to use layers and region updates) --- #

# REGION-BASED DRAWING SYSTEM USAGE:
# 
# The display system now supports efficient partial screen updates. Here's how to use it:
#
# 1. BASIC DRAWING (automatically marks regions dirty):
#    - context["drawing"]["draw_text"](text, x, y, font, fill)
#    - context["drawing"]["draw_image"](img, x, y) 
#    - context["drawing"]["draw_area"](x, y, width, height, fill)
#
# 2. OVERLAY DRAWING (for temporary/dynamic content):
#    - context["drawing"]["draw_overlay_text"](text, x, y, font, fill)
#    - context["drawing"]["draw_overlay_image"](img, x, y)
#    - context["drawing"]["draw_overlay_area"](x, y, width, height, fill)
#
# 3. CLEARING REGIONS:
#    - context["drawing"]["clear_area"](x, y, width, height)
#    - context["drawing"]["clear_overlay_area"](x, y, width, height)
#
# 4. MANUAL REGION UPDATES (for advanced usage):
#    - context["drawing"]["mark_dirty"](x, y, width, height)
#    - context["drawing"]["update_region"](x, y, width, height)
#
# 5. BATCHING FOR HARDWARE PERFORMANCE:
#    - context["drawing"]["begin_batch"]() - Start batching operations
#    - context["drawing"]["end_batch"]() - Execute all batched operations at once
#
# PERFORMANCE TIPS:
# - Use overlay layer for frequently changing content (cursors, animations)
# - Use base layer for static content (text, backgrounds) 
# - Group nearby changes to reduce the number of dirty regions
# - Use begin_batch/end_batch for drawing multiple items at once (reduces hardware updates)
# - Only update regions that actually changed

# Batching system for hardware performance
_batch_mode = False
_batch_operations = []

def begin_batch():
    """Start batching drawing operations to reduce hardware updates"""
    global _batch_mode, _batch_operations
    _batch_mode = True
    _batch_operations = []

def end_batch():
    """Execute all batched operations at once"""
    global _batch_mode, _batch_operations
    if not _batch_mode:
        return
    
    _batch_mode = False
    
    # Execute all batched operations
    for op_type, args in _batch_operations:
        if op_type == "text":
            layer, font, text, x, y, fill = args
            display_draw_text_immediate(layer, font, text, x, y, fill)
        elif op_type == "text_inverted":
            layer_draw, layer_image, font, text, x, y, padding = args
            display_draw_text_inverted_immediate(layer_draw, layer_image, font, text, x, y, padding)
        elif op_type == "area":
            layer, x, y, width, height, fill = args
            display_draw_area_immediate(layer, x, y, width, height, fill)
        elif op_type == "icon":
            layer, icon_img, x, y = args
            display_draw_icon_immediate(layer, icon_img, x, y)
    
    _batch_operations = []
    
    # Single update at the end
    update_display(force=True)

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
        title_width_calc, title_height = get_text_size(title, fontSmall)
        draw_text_aligned(base_draw, title, x + width/2 - title_width/2, title_top, fontSmall, 255)

        startY = top + title_height + padding
        max_lines = (height - startY) // bodyLineHeight
        for i in range(min(len(wrapped_lines), max_lines)):
            draw_text_aligned(base_draw, wrapped_lines[i], x, startY + i * bodyLineHeight, fontSmall, 255)
            # Store previous position before updating
            prevDrawY = lastDrawY
            prevDrawX = lastDrawX
            # Update cursor position
            lastDrawY = startY + i * bodyLineHeight
            lastDrawX = base_draw.textlength(wrapped_lines[i], font=fontSmall)
        mark_display_dirty()
        # Force immediate update for screen changes to prevent black screens
        update_display(force=True)

def display_draw_text_immediate(layer, font, text, x=0, y=0, fill=255):
    """Draw text immediately without batching - used internally"""
    with draw_lock:
        draw_text_aligned(layer, text, x, y, font, fill)
        # Calculate text dimensions for dirty region
        text_width, text_height = get_text_size(text, font)
        mark_display_dirty(x, y, text_width, text_height)
        
        # Add debug region visualization (Windows only)
        if IS_WINDOWS and hasattr(disp, 'add_debug_region'):
            disp.add_debug_region(int(x), int(y), int(text_width), int(text_height))

def display_draw_text(layer, font, text, x=0, y=0, fill=255):
    """Draw text with optional batching support"""
    if _batch_mode:
        _batch_operations.append(("text", (layer, font, text, x, y, fill)))
    else:
        display_draw_text_immediate(layer, font, text, x, y, fill)

def display_draw_text_inverted_immediate(layer_draw, layer_image, _font, text, x=0, y=0, padding=1):
    """Draw inverted text (white background, black text) immediately without batching"""
    with draw_lock:
        # Get text dimensions
        text_width, text_height = get_text_size(text, _font)
        
        # Calculate background rectangle dimensions with padding
        bg_width = text_width + (padding * 2)
        bg_height = text_height + (padding * 2)
        bg_x = x - padding
        bg_y = y - padding
        
        # Draw white background rectangle

        layer_draw.rectangle([bg_x, bg_y, bg_x + bg_width, bg_y + bg_height], fill=255)
        
        if _font == fontSmall:
            # Adjust y position for small font
            y -= 1
        
        # Draw black text on top
        layer_draw.text((x, y), text, font=_font, fill=0)
        
        # Mark the region as dirty for update
        add_dirty_region(bg_x, bg_y, bg_width, bg_height)
        
        # Add debug region if enabled
        if IS_WINDOWS and hasattr(disp, 'add_debug_region'):
            disp.add_debug_region(int(bg_x), int(bg_y), int(bg_width), int(bg_height))

def display_draw_text_inverted(layer_draw, layer_image, font, text, x=0, y=0, padding=1):
    """Draw inverted text with optional batching support"""
    if _batch_mode:
        _batch_operations.append(("text_inverted", (layer_draw, layer_image, font, text, x, y, padding)))
    else:
        display_draw_text_inverted_immediate(layer_draw, layer_image, font, text, x, y, padding)

def display_draw_icon_immediate(layer, icon_img, x=0, y=height - 8):
    """Draw icon immediately without batching - used internally"""
    with draw_lock:
        # Icon should already be converted to mode "1" from cache
        if icon_img and icon_img.mode != "1":
            icon_img = icon_img.convert("1")
        if icon_img:
            layer.paste(icon_img, (x, y), icon_img)
            # Mark icon area as dirty
            mark_display_dirty(x, y, icon_img.width, icon_img.height)
            
            # Add debug region visualization (Windows only)
            if IS_WINDOWS and hasattr(disp, 'add_debug_region'):
                disp.add_debug_region(int(x), int(y), int(icon_img.width), int(icon_img.height))

def display_draw_icon(layer, icon_img, x=0, y=height - 8):
    """Draw icon with optional batching support"""
    if _batch_mode:
        _batch_operations.append(("icon", (layer, icon_img, x, y)))
    else:
        display_draw_icon_immediate(layer, icon_img, x, y)

def display_draw_area_immediate(layer, x=0, y=0, width=128, height=64, fill=255):
    """Draw area immediately without batching - used internally"""
    with draw_lock:
        layer.rectangle((x, y, x + width - 1, y + height - 1), fill=fill)
        mark_display_dirty(x, y, width, height)
        
        # Add debug region visualization (Windows only)
        if IS_WINDOWS and hasattr(disp, 'add_debug_region'):
            disp.add_debug_region(int(x), int(y), int(width), int(height))
        
def display_draw_area(layer, x=0, y=0, width=128, height=64, fill=255):
    """Draw area with optional batching support"""
    if _batch_mode:
        _batch_operations.append(("area", (layer, x, y, width, height, fill)))
    else:
        display_draw_area_immediate(layer, x, y, width, height, fill)

def display_draw_blinking_cursor(x, y, isOn):
    global current_app_cursor_enabled, cursor_state_changed, last_cursor_visible_state, prevDrawX, prevDrawY
    with draw_lock:
        # Check if cursor should be visible
        cursor_should_be_visible = cursor_enabled and current_app_cursor_enabled
        
        # Clear previous cursor position if position changed
        if (int(x) != int(prevDrawX) or int(y) != int(prevDrawY)) and cursor_should_be_visible:
            # Clear old cursor position
            base_draw_2.rectangle((int(prevDrawX)+2, int(prevDrawY), int(prevDrawX)+3, int(prevDrawY)+cursor_height), fill=0)
            mark_display_dirty(int(prevDrawX)+2, int(prevDrawY), 1, cursor_height)
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
            
            mark_display_dirty(int(x) + 1, int(y), cursor_width, cursor_height)
            last_cursor_visible_state = cursor_should_be_visible
            cursor_state_changed = False
        elif cursor_should_be_visible:
            # Only blink if cursor is visible
            color = 255 if isOn else 0
            base_draw_2.rectangle((int(x) + 1, int(y), int(x) + 1 + cursor_width, int(y) + cursor_height), fill=color)
            mark_display_dirty(int(x) + 1, int(y), cursor_width, cursor_height)

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
        mark_display_dirty(int(lastDrawX)+1, int(lastDrawY), cursor_width, cursor_height)
        # Clear previous cursor position if different
        if prevDrawX != lastDrawX or prevDrawY != lastDrawY:
            base_draw_2.rectangle((int(prevDrawX)+1, int(prevDrawY), int(prevDrawX)+1+cursor_width, int(prevDrawY)+cursor_height), fill=0)
            mark_display_dirty(int(prevDrawX)+1, int(prevDrawY), cursor_width, cursor_height)

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
                        if len(cmd) == 6:
                            _, font, text, x, y, fill = cmd
                        else:
                            _, font, text, x, y = cmd
                            fill = 255  # Default fill color
                        display_draw_text(base_draw, font, text, x, y, fill=fill)
                    case "draw_overlay_text":
                        if len(cmd) == 6:
                            _, font, text, x, y, fill = cmd
                        else:
                            _, font, text, x, y = cmd
                            fill = 255  # Default fill color
                        display_draw_text(overlay_draw, font, text, x, y, fill=fill)
                    case "draw_base_text_inverted":
                        if len(cmd) == 6:
                            _, font, text, x, y, padding = cmd
                        else:
                            _, font, text, x, y = cmd
                            padding = 1  # Default padding
                        display_draw_text_inverted(base_draw, base_layer, font, text, x, y, padding=padding)
                    case "draw_overlay_text_inverted":
                        if len(cmd) == 6:
                            _, font, text, x, y, padding = cmd
                        else:
                            _, font, text, x, y = cmd
                            padding = 1  # Default padding
                        display_draw_text_inverted(overlay_draw, overlay_layer, font, text, x, y, padding=padding)
                    case "draw_base_image":
                        _, img, x, y = cmd
                        display_draw_icon(base_layer, img, x, y)
                    case "draw_overlay_image":
                        _, img, x, y = cmd
                        display_draw_icon(overlay_layer, img, x, y)
                    case "clear_base":
                        display_draw_area(base_draw, 0, 0, 128, 64, fill=0)
                        update_display(force=True)
                    case "clear_base_2":
                        display_draw_area(base_draw_2, 0, 0, 128, 64, fill=0)
                        update_display(force=True)
                    case "clear_base_area":
                        _, x, y, width, height = cmd
                        display_draw_area(base_draw, x, y, width, height, fill=0)
                    case "draw_base_area":
                        _, x, y, width, height, fill = cmd
                        display_draw_area(base_draw, x, y, width, height, fill=fill)
                    case "draw_overlay_area":
                        _, x, y, width, height, fill = cmd
                        display_draw_area(overlay_draw, x, y, width, height, fill=fill)
                    case "clear_overlay_area":
                        _, x, y, width, height = cmd
                        display_draw_area(overlay_draw, x, y, width, height, fill=0)
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
                    case "update_region":
                        _, x, y, width, height = cmd
                        update_display(region=(x, y, width, height))
                    case "begin_batch":
                        begin_batch()
                    case "end_batch":
                        end_batch()
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

# Initialize TTS Engine Manager
tts_manager = TTSEngineManager(PIPER_BIN, MODEL_PATH, VOICEVOX_BIN, VOICEVOX_HOST, VOICEVOX_PORT)
atexit.register(lambda: tts_manager.close_all())

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

# Initialize Pygame mixer for all platforms
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
            # Check if audio is already in WAV format (starts with RIFF header)
            if audio_bytes.startswith(b'RIFF'):
                # Already WAV format (VoiceVox)
                wav_buf = io.BytesIO(audio_bytes)
            else:
                # Raw PCM format (Piper) - convert to WAV
                wav_buf = wrap_raw_audio_as_wav(audio_bytes)
            
            sound = pygame.mixer.Sound(wav_buf)
            channel = sound.play()
            while channel.get_busy():
                pygame.time.wait(10)
        except Exception as e:
            print(f"[Audio] Pygame playback error: {e}", flush=True)
    else:
        try:
            # Check if audio is already in WAV format
            if audio_bytes.startswith(b'RIFF'):
                # WAV format - use aplay directly
                proc = subprocess.Popen(["timeout", "5", "aplay", "-"], stdin=subprocess.PIPE)
                proc.communicate(input=audio_bytes)
            else:
                # Raw PCM format - specify format parameters
                proc = subprocess.Popen([
                    "timeout", "5",
                    "aplay", "-R", "400", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"
                ], stdin=subprocess.PIPE)
                proc.communicate(input=audio_bytes)
        except Exception as e:
            print(f"[Audio] aplay error: {e}", flush=True)

def run_tts(text, background=False):
    """
    Generate and play TTS audio with intelligent caching.
    
    Cache keys include TTS engine, VoiceVox speaker ID, and Piper model
    to ensure cached audio matches the current voice/style configuration.
    """
    if not text.strip():
        return
    
    # Create cache key based on text, current TTS engine, and voice/style
    engine_suffix = f"_{tts_manager.get_current_engine()}"
    
    # Add voice/model specific information to cache key
    if tts_manager.get_current_engine() == "voicevox":
        # Include VoiceVox speaker ID to ensure correct voice caching
        from config.user_preferences import user_preferences
        speaker_id = user_preferences.get_voicevox_speaker_id() if user_preferences else 2
        engine_suffix += f"_speaker_{speaker_id}"
    elif tts_manager.get_current_engine() == "piper":
        # Include Piper model path to handle different models
        model_filename = os.path.basename(MODEL_PATH) if MODEL_PATH else "unknown"
        engine_suffix += f"_model_{model_filename}"
    
    cache_key = hash_text(text + engine_suffix)
    cached_file = os.path.join(CACHE_DIR, cache_key + ".raw")

    if os.path.exists(cached_file):
        with open(cached_file, "rb") as f:
            cached_audio = f.read()

        if not background:
            display_queue.put(("set_screen", f"Cached ({tts_manager.get_current_engine().title()})", text))
            display_queue.put(("draw_icon", speaking_icon, 0, height - 8))
        
        # For cached audio, we always have raw PCM format, so wrap as WAV if needed
        if tts_manager.get_current_engine() == "voicevox":
            # Convert raw PCM back to WAV for VoiceVox playback compatibility
            audio_to_play = wrap_raw_audio_as_wav(cached_audio).getvalue()
        else:
            audio_to_play = cached_audio
            
        play_thread = threading.Thread(target=play_audio_sync, args=(audio_to_play,))
        play_thread.start()
        play_thread.join()
        if not background:
            display_queue.put(("clear_icon",))

    else:
        if not background:
            display_queue.put(("set_screen", f"Generating ({tts_manager.get_current_engine().title()})", text))
            display_queue.put(("draw_icon", generating_icon, 0, height - 8))

        try:
            mappedText = apply_word_map(text, word_map)
            raw_audio = tts_manager.synthesize(mappedText)
            if not background:
                display_queue.put(("clear_icon",))

            if raw_audio:
                # Handle different audio formats for caching
                audio_to_cache = raw_audio
                if tts_manager.get_current_engine() == "voicevox":
                    # VoiceVox returns WAV format, extract raw PCM for consistent caching
                    try:
                        wav_buffer = io.BytesIO(raw_audio)
                        with wave.open(wav_buffer, 'rb') as wav_file:
                            audio_to_cache = wav_file.readframes(wav_file.getnframes())
                    except Exception as e:
                        print(f"[TTS] Failed to extract raw audio from WAV: {e}")
                        # Use original audio data if extraction fails
                        audio_to_cache = raw_audio
                
                # Cache the processed audio
                with open(cached_file, "wb") as f:
                    f.write(audio_to_cache)

                if not background:
                    display_queue.put(("set_screen", f"Talking ({tts_manager.get_current_engine().title()})", text))
                    display_queue.put(("draw_icon", speaking_icon, 0, height - 8))
                
                # Play the original audio (preserves format)
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
        def __init__(self, display_instance):
            self.display = display_instance
            
        def read_loop(self):
            while True:
                kb_event = keyboard.read_event()
                if kb_event.event_type in ("down", "up"):
                    # Only yield events if the emulator window is focused
                    if self.display and self.display.is_window_focused():
                        yield EvdevLikeEvent(kb_event)
                    # Small delay to prevent busy waiting when not focused
                    elif not self.display.is_window_focused():
                        import time
                        time.sleep(0.01)

    def wait_for_keyboard():
        return WindowsInputDevice(disp)
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
def get_text_size(text, _font):
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
    bbox = temp_draw.textbbox((0, 0), text, font=_font)
    
    # bbox returns (left, top, right, bottom)
    # For consistent behavior, we want the actual rendered size
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    
    # Ensure we return positive values
    width = max(0, width)
    height = max(0, height)
    
    if _font == fontSmall:
        # For small font, we want to ensure it fits within the expected line height
        height = 4
        width -= 1
    elif _font == font:
        height = 9
        width -= 1
    
    return width, height

def get_text_baseline_offset(font):
    if font == fontSmall:
        return 1
    elif font == fontLarge:
        return 5
    elif font == font:
        return 0
    else:
        return 0

def draw_text_aligned(layer, text, x, y, font, fill=255):
    """
    Draw text with proper alignment compensation for PIL's positioning changes.
    """
    # Get the baseline offset to compensate for PIL's text positioning
    offset = get_text_baseline_offset(font)
    # Adjust y position by the offset to align text properly
    adjusted_y = y - offset
    layer.text((x, adjusted_y), text, font=font, fill=fill)

# --- Context drawing functions that return size --- #

def draw_text_with_size(text, x, y, font=None, fill=255):
    """Draw text on base layer and return (width, height) of drawn text"""
    actual_font = font or fontSmall
    display_queue.put(("draw_base_text", actual_font, text, x, y, fill))
    return get_text_size(text, actual_font)

def draw_text_inverted_with_size(text, x, y, font=None, padding=1):
    """Draw inverted text on base layer and return (width, height) of drawn area including padding"""
    actual_font = font or fontSmall
    display_queue.put(("draw_base_text_inverted", actual_font, text, x, y, padding))
    text_width, text_height = get_text_size(text, actual_font)
    # Include padding in the returned size
    return (text_width + (padding * 2), text_height + (padding * 2))

def draw_overlay_text_with_size(text, x, y, font=None, fill=255):
    """Draw text on overlay layer and return (width, height) of drawn text"""
    actual_font = font or fontSmall
    display_queue.put(("draw_overlay_text", actual_font, text, x, y, fill))
    return get_text_size(text, actual_font)

def draw_overlay_text_inverted_with_size(text, x, y, font=None, padding=1):
    """Draw inverted text on overlay layer and return (width, height) of drawn area including padding"""
    actual_font = font or fontSmall
    display_queue.put(("draw_overlay_text_inverted", actual_font, text, x, y, padding))
    text_width, text_height = get_text_size(text, actual_font)
    # Include padding in the returned size
    return (text_width + (padding * 2), text_height + (padding * 2))

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
        display_queue.put(("set_screen", "Warning", f"Piper binary not found at:\n{PIPER_BIN}\nVoiceVox only mode."))
        time.sleep(3)
    if not os.path.isfile(MODEL_PATH):
        display_queue.put(("set_screen", "Warning", f"Piper model not found at:\n{MODEL_PATH}\nVoiceVox only mode."))
        time.sleep(3)
    
    # Check VoiceVox binary (optional)
    if not os.path.isfile(VOICEVOX_BIN):
        print(f"[Main] VoiceVox binary not found at: {VOICEVOX_BIN} (optional)")
    else:
        print(f"[Main] VoiceVox binary found at: {VOICEVOX_BIN}")

    display_queue.put(("set_screen", "Starting", "Please wait..."))

    currentline = ""

    shift_key_left = 'KEY_LEFTSHIFT'
    shift_key_right = 'KEY_RIGHTSHIFT'
    keys_pressed = set()
    
    context = {
        "emulator": IS_WINDOWS,
        "display": disp,
        "screen_width": width,
        "screen_height": height,
        "pressed_keys": keys_pressed,
        "load_icon": load_icon,
        "audio": {
            "play_sfx": play_sfx,
            "play_music": play_music,
            "stop_music": stop_music,
            "set_music_volume": set_music_volume,
            # Audio streaming functions
            "start_stream": start_audio_stream,
            "pause_stream": pause_audio_stream,
            "resume_stream": resume_audio_stream,
            "stop_stream": stop_audio_stream,
            "set_stream_volume": set_audio_stream_volume,
            "get_stream_position": get_audio_stream_position,
            "is_stream_playing": is_audio_stream_playing,
            "is_stream_paused": is_audio_stream_paused,
            "get_stream_info": get_audio_stream_info,
        },
        "tts": {
            "run": run_tts,
            "set_engine": lambda engine: tts_manager.set_engine(engine),
            "get_engine": lambda: tts_manager.get_current_engine(),
            "set_voicevox_speaker": lambda speaker_id: tts_manager.set_voicevox_speaker(speaker_id),
            "get_available_engines": lambda: ["piper", "voicevox"],
            "get_voicevox_speakers": lambda: tts_manager.get_voicevox_speakers(),
            "get_voicevox_speakers_flat": lambda: tts_manager.get_voicevox_speakers_flat(),
            "refresh_voicevox_speakers": lambda: tts_manager.refresh_voicevox_speakers_cache(),
        },
        "fonts": {
            "small": fontSmall,
            "default": font,
            "large": fontLarge,
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
        # New region-based drawing functions for apps
        "drawing": {
            # Base layer drawing (static content)
            "draw_text": draw_text_with_size,
            "draw_text_inverted": draw_text_inverted_with_size,
            "draw_image": lambda img, x, y: display_queue.put(("draw_base_image", img, x, y)),
            "draw_area": lambda x, y, width, height, fill=255: display_queue.put(("draw_base_area", x, y, width, height, fill)),
            "clear_area": lambda x, y, width, height: display_queue.put(("clear_base_area", x, y, width, height)),
            "clear_screen": lambda: display_queue.put(("clear_base",)),
            
            # Overlay layer drawing (temporary/dynamic content)
            "draw_overlay_text": draw_overlay_text_with_size,
            "draw_overlay_text_inverted": draw_overlay_text_inverted_with_size,
            "draw_overlay_image": lambda img, x, y: display_queue.put(("draw_overlay_image", img, x, y)),
            "draw_overlay_area": lambda x, y, width, height, fill=255: display_queue.put(("draw_overlay_area", x, y, width, height, fill)),
            "clear_overlay_area": lambda x, y, width, height: display_queue.put(("clear_overlay_area", x, y, width, height)),
            
            # Hardware performance optimization (batching)
            "begin_batch": lambda: display_queue.put(("begin_batch",)),
            "end_batch": lambda: display_queue.put(("end_batch",)),
            
            # Region-based updates (for efficiency)
            "update_region": lambda x, y, width, height: display_queue.put(("update_region", x, y, width, height)),
            "mark_dirty": lambda x, y, width, height: mark_display_dirty(x, y, width, height),
        },
        "get_text_size": get_text_size,
        "hash_text": hash_text,
        "FONT_PATH": FONT_PATH,
        "CACHE_DIR": CACHE_DIR,
        "CONFIG_DIR": CONFIG_DIR,
        "APPS_DIR": APPS_DIR,
        "OVERLAY_DIR": OVERLAY_DIR,
        "AUTOCOMPLETE_PATH": AUTOCOMPLETE_PATH,
    }
    
    # Initialize user preferences
    from config.user_preferences import initialize_preferences
    user_prefs = initialize_preferences(CONFIG_DIR)
    context["user_preferences"] = user_prefs
    
    # Set TTS engine based on user preferences
    preferred_engine = user_prefs.get_tts_engine()
    if tts_manager.set_engine(preferred_engine):
        print(f"[Main] TTS engine set to: {preferred_engine}")
    else:
        print(f"[Main] Failed to set TTS engine to: {preferred_engine}, using default")
    
    # Create and use the reusable AppManager
    from app_manager import AppManager
    app_manager = AppManager(APPS_DIR, OVERLAY_DIR, context)

    # Load all overlays
    overlay_count = app_manager.load_overlays(apps)
    print(f"[Main] Loaded {overlay_count} overlay apps")
    
    # Start all loaded overlays (unless disabled by user)
    for overlay_name in app_manager.overlay_apps:
        # Check if overlay is disabled in user preferences
        if user_prefs.is_overlay_disabled(overlay_name):
            print(f"[Main] Skipping disabled overlay: {overlay_name}")
            continue
            
        if app_manager.start_app(overlay_name, update_rate_hz=20.0):
            print(f"[Main] Started overlay: {overlay_name}")
        else:
            print(f"[Main] Failed to start overlay: {overlay_name}")

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
                            
                            if shift_key_left in keys_pressed or shift_key_right in keys_pressed:
                                print("Key pressed + shift:", keycode)
                                tmp = shift_key_map.get(keycode, None)
                                if tmp is not None:
                                    keycode = tmp
                            app_manager.distribute_event("onkeydown", keycode)
                            
                        elif key_event.keystate == 0: # Key up
                            if keycode in keys_pressed:
                                keys_pressed.remove(keycode)

                                if shift_key_left in keys_pressed or shift_key_right in keys_pressed:
                                    print("Key pressed + shift:", keycode)
                                    tmp = shift_key_map.get(keycode, None)
                                    if tmp is not None:
                                        keycode = tmp
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