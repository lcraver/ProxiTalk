import os
import time
import hashlib
import threading
import math
import queue
import atexit
import re
import json
import traceback
import platform
import io
import wave
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont
from emulator_display import create_display
from audio_manager import (
    initialize_audio_system,
    play_sfx,
    play_music,
    stop_music,
    set_music_volume,
    start_audio_stream,
    pause_audio_stream,
    resume_audio_stream,
    stop_audio_stream,
    set_audio_stream_volume,
    get_audio_stream_position,
    is_audio_stream_playing,
    is_audio_stream_paused,
    get_audio_stream_info,
    wrap_raw_audio_as_wav,
    play_audio_sync,
)
from tts_engines.base import EngineResources
from tts_engine_manager import TTSEngineManager as ModularTTSEngineManager
from keyboard_manager import KeyboardManager, KEY_DOWN, KEY_UP
from utils.image_utils import AppImageUtils
from sleep_manager import SleepController

# --- Constants --- #

IS_WINDOWS = platform.system() == "Windows"
DEFAULT_AUTO_SLEEP_MINUTES = 5.0

# I2C settings for luma.oled (Linux only)
I2C_PORT = 1        # I2C port (usually 1 on Raspberry Pi)
I2C_ADDRESS = 0x3C  # Common I2C address for SSD1306 displays

if IS_WINDOWS:
    from config.emulator.paths import PIPER_BIN, MODEL_PATH, VOICEVOX_BIN, VOICEVOX_HOST, VOICEVOX_PORT, OPENJTALK_HTSVOICE_DIR, CACHE_DIR, CONFIG_DIR, APPS_DIR, ICON_DIR, AUTOCOMPLETE_PATH
    from config.emulator.paths import FONT_PATH, FONT_SMALL_PATH, OVERLAY_DIR, FILES_DIR
else:
    from config.paths import PIPER_BIN, MODEL_PATH, VOICEVOX_BIN, VOICEVOX_HOST, VOICEVOX_PORT, OPENJTALK_HTSVOICE_DIR, CACHE_DIR, CONFIG_DIR, APPS_DIR, ICON_DIR, AUTOCOMPLETE_PATH
    from config.paths import FONT_PATH, FONT_SMALL_PATH, OVERLAY_DIR, FILES_DIR
    
# -- Emulator Setup --- #

def is_admin():
    if not IS_WINDOWS:
        return True  # Assume admin on non-Windows
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

disp = create_display(IS_WINDOWS, 128, 64, ICON_DIR, I2C_PORT, I2C_ADDRESS)
disp.contrast(255)


# --- Application Setup --- #

import importlib.util
import json
import traceback
from interfaces import AppBase

apps = []
loaded_apps = {}

APP_DIRECTORY_SKIP = {"__pycache__"}
app_path_lookup = {}

def resolve_app_relative_path(identifier: str) -> str:
    """Map an app identifier to its relative filesystem path inside APPS_DIR."""
    if not identifier:
        return ""
    normalized = os.path.normpath(identifier)
    return app_path_lookup.get(identifier, normalized)

def discover_app_directories(base_dir: str, relative_path: Optional[str] = None) -> List[str]:
    """Recursively discover all app directories containing a main.py file."""
    discovered: List[str] = []
    try:
        with os.scandir(base_dir) as entries:
            for entry in entries:
                if not entry.is_dir(follow_symlinks=False):
                    continue

                name = entry.name
                if name.startswith('.') or name in APP_DIRECTORY_SKIP:
                    continue

                next_relative = os.path.join(relative_path, name) if relative_path else name
                next_relative = os.path.normpath(next_relative)
                main_path = os.path.join(entry.path, "main.py")

                if os.path.isfile(main_path):
                    discovered.append(next_relative)
                else:
                    discovered.extend(discover_app_directories(entry.path, next_relative))
    except FileNotFoundError:
        print(f"[Loader] Apps directory not found: {base_dir}")
    return discovered

def load_apps():
    apps = []
    for relative_path in sorted(discover_app_directories(APPS_DIR)):
        folder = os.path.basename(relative_path)
        apps.append({
            "name": folder,
            "path": relative_path,
            "metadata": load_metadata(relative_path),
            "icon_normal": load_icon(relative_path),
            "icon_selected": load_icon(relative_path, "selected"),
        })
    return apps

def load_icon(app_identifier, state=None):
    relative_path = resolve_app_relative_path(app_identifier)
    if state:
        icon_path = os.path.join(APPS_DIR, relative_path, f"icon_{state}.png")
    else:
        icon_path = os.path.join(APPS_DIR, relative_path, "icon.png")
        
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
        relative_path = resolve_app_relative_path(app_name)
        app_dir = os.path.join(APPS_DIR, relative_path)
        path = os.path.join(app_dir, "main.py")
        if not os.path.isfile(path):
            print(f"[Error] App file not found for '{app_name}' (looked in {path})")
            return None
        spec = importlib.util.spec_from_file_location(f"{app_name}.main", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if not hasattr(mod, "App"):
            raise AttributeError("No 'App' class found")

        if context is not None:
            context["app_path"] = os.path.join(app_dir, "")

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
apps_by_name = {}
app_path_lookup = {}

for app in apps:
    slug = app.get("name")
    if not slug:
        continue
    relative_path = app.get("path") or slug
    if slug in apps_by_name:
        existing_path = apps_by_name[slug].get("path")
        print(f"[Loader] Duplicate app name detected: {slug} ({existing_path} vs {relative_path})")
    apps_by_name[slug] = app
    app_path_lookup[slug] = os.path.normpath(relative_path)

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
        
    relative_path = resolve_app_relative_path(app_name)
    if state:
        icon_path = os.path.join(APPS_DIR, relative_path, f"icon_{state}.png")
    else:
        icon_path = os.path.join(APPS_DIR, relative_path, "icon.png")
        
    if os.path.isfile(icon_path):
        img = Image.open(icon_path).convert("1")
        # Cache the converted icon
        _icon_cache[cache_key] = img
        return img
    
    return None

searching_icon = load_base_icon("info")
generating_icon = load_base_icon("settings")
speaking_icon = load_base_icon("notes")


# --- TTS Engines --- #
# Implementations now live in tts_engines/ and are loaded dynamically.

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
        bg_height -= 1  # Adjust background y for small font
        bg_x = x - padding
        bg_y = y - padding
        
        if _font == fontSmall:
            # Adjust y position for small font
            y -= 1
        
        # Draw white background rectangle

        layer_draw.rectangle([bg_x, bg_y, bg_x + bg_width, bg_y + bg_height], fill=255)
        
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

def play_startup_sequence():
    """Play startup.wav alongside startup.gif before the launcher appears."""
    startup_dir = os.path.dirname(__file__)
    audio_path = os.path.join(startup_dir, "startup.wav")
    gif_path = os.path.join(startup_dir, "startup.gif")

    audio_duration = 0.0
    audio_started = False

    if os.path.exists(audio_path):
        try:
            with wave.open(audio_path, "rb") as wav_file:
                frames = wav_file.getnframes()
                framerate = wav_file.getframerate() or 1
                audio_duration = frames / float(framerate or 1)
            print("[Main] Playing startup sfx: プロキトク...")
            play_sfx(audio_path)
            audio_started = True
        except Exception as exc:
            print(f"[Main] Failed to play startup sfx: {exc}")
    else:
        print("[Main] No startup audio found")

    gif_frames: List[Image.Image] = []
    gif_durations: List[float] = []
    if os.path.exists(gif_path):
        try:
            with Image.open(gif_path) as gif_image:
                animation = AppImageUtils.prepare_animation_frames(
                    gif_image,
                    max_width=width,
                    max_height=height,
                    allow_upscale=True,
                )
            gif_frames = animation.get("frames", [])
            gif_durations = [max(0.05, duration / 1000.0) for duration in animation.get("durations", [])]
            if gif_frames:
                print(f"[Main] Loaded startup animation ({len(gif_frames)} frames)")
        except Exception as exc:
            print(f"[Main] Failed to load startup animation: {exc}")
    else:
        print("[Main] No startup animation found")

    if not gif_frames:
        if audio_started and audio_duration > 0:
            time.sleep(audio_duration)
        return

    animation_cycle = sum(gif_durations) if gif_durations else 0.0
    if animation_cycle <= 0:
        animation_cycle = len(gif_frames) * 0.08

    if audio_duration > 0:
        sequence_duration = max(audio_duration, animation_cycle)
    else:
        sequence_duration = animation_cycle

    display_queue.put(("clear_overlay_area", 0, 0, width, height))
    display_queue.put(("clear_base_area", 0, 0, width, height))

    start_time = time.monotonic()
    frame_index = 0
    total_frames = len(gif_frames)

    while True:
        frame = gif_frames[frame_index]
        pos_x = max(0, (width - frame.width) // 2)
        pos_y = max(0, (height - frame.height) // 2)
        display_queue.put(("clear_base_area", 0, 0, width, height))
        display_queue.put(("draw_base_image", frame, pos_x, pos_y))

        sleep_time = gif_durations[frame_index] if gif_durations else 0.08
        time.sleep(sleep_time)

        elapsed = time.monotonic() - start_time
        if sequence_duration > 0 and elapsed >= sequence_duration:
            break

        frame_index = (frame_index + 1) % total_frames
        if audio_duration <= 0 and frame_index == 0:
            break

    display_queue.put(("clear_base_area", 0, 0, width, height))

# --- TTS + Cache --- #

os.makedirs(CACHE_DIR, exist_ok=True)

from config.wordmap import word_map
from utils.japanese import convert_romanji_to_hiragana

# Initialize user preferences first so TTS manager can access preferred models
from config.user_preferences import initialize_preferences
user_preferences = initialize_preferences(CONFIG_DIR)

# Ensure launcher defaults to the Proxi app on fresh startup
if user_preferences:
    try:
        if user_preferences.get_last_launched_app() != "proxi":
            user_preferences.set_last_launched_app("proxi")
    except Exception as exc:
        print(f"[Main] Failed to set default launcher app: {exc}")

auto_sleep_minutes = user_preferences.get_auto_sleep_minutes(DEFAULT_AUTO_SLEEP_MINUTES) if user_preferences else 0.0
auto_sleep_seconds = max(0.0, float(auto_sleep_minutes)) * 60.0

# Initialize TTS Engine Manager
engine_resources = EngineResources(
    is_windows=IS_WINDOWS,
    cache_dir=CACHE_DIR,
    config_dir=CONFIG_DIR,
    user_preferences=user_preferences,
    paths={
        "piper_bin": PIPER_BIN,
        "default_piper_model": MODEL_PATH,
        "voicevox_bin": VOICEVOX_BIN,
        "voicevox_host": VOICEVOX_HOST,
        "voicevox_port": VOICEVOX_PORT,
        "openjtalk_htsvoice_dir": OPENJTALK_HTSVOICE_DIR,
    },
)
preferred_engine = user_preferences.get_tts_engine() if user_preferences else None
tts_manager = ModularTTSEngineManager(engine_resources, preferred_engine=preferred_engine)
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


def preprocess_tts_text(text, engine_id=None):
    """Normalize text before synthesis based on the active engine."""
    normalized_text = apply_word_map(text, word_map)
    current_engine = engine_id or tts_manager.get_current_engine()

    if current_engine in {"voicevox", "openjtalk"}:
        converted_text = convert_romanji_to_hiragana(normalized_text)
        if converted_text != normalized_text:
            print(
                f"[TTS] Preprocessed Japanese text for {current_engine}: "
                f"'{normalized_text}' -> '{converted_text}'"
            )
        return converted_text

    return normalized_text

# Initialize shared audio system for playback and caching helpers
initialize_audio_system()

def run_tts(text, background=False, skip_cache=False):
    """
    Generate and play TTS audio with intelligent caching.
    
    Cache keys include TTS engine, VoiceVox speaker ID, and Piper model
    to ensure cached audio matches the current voice/style configuration.
    
    Args:
        text: Text to synthesize
        background: If True, don't update display during synthesis
        skip_cache: If True, bypass cache and force fresh synthesis
    """
    if not text.strip():
        return
    
    # Create cache key based on text, current TTS engine, and engine-specific identity info
    current_engine = tts_manager.get_current_engine()
    processed_text = preprocess_tts_text(text, current_engine)
    engine_suffix = f"_{current_engine}" if current_engine else ""

    identity = tts_manager.get_cache_identity()
    for key, value in sorted(identity.items()):
        engine_suffix += f"_{key}-{value}"
    
    cache_key = hash_text(processed_text + engine_suffix)
    cached_file = os.path.join(CACHE_DIR, cache_key + ".raw")

    # Check cache only if not skipping cache
    if not skip_cache and os.path.exists(cached_file):
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
            if skip_cache:
                display_queue.put(("set_screen", f"Testing ({tts_manager.get_current_engine().title()})", text))
            else:
                display_queue.put(("set_screen", f"Generating ({tts_manager.get_current_engine().title()})", text))
            display_queue.put(("draw_icon", generating_icon, 0, height - 8))

        try:
            raw_audio = tts_manager.synthesize(processed_text)
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

if IS_WINDOWS:
    from config.emulator.win_keycodes import WIN_TO_LINUX_KEYCODE
else:
    WIN_TO_LINUX_KEYCODE = None


def apply_shift_mapping(keycode, keys_pressed, shift_left, shift_right):
    """Return mapped keycode when a shift modifier is active."""
    if shift_left in keys_pressed or shift_right in keys_pressed:
        mapped = shift_key_map.get(keycode)
        if mapped:
            print("Key pressed + shift:", keycode)
            return mapped
    return keycode

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
        return 3
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
    wake_keycode = 'KEY_SPACE'
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
            "set_engine": tts_manager.set_engine,
            "get_engine": tts_manager.get_current_engine,
            "get_available_engines": tts_manager.get_available_engine_ids,
            "get_all_engines": tts_manager.get_all_engine_ids,
            "get_disabled_engines": tts_manager.get_disabled_engine_ids,
            "set_disabled_engines": tts_manager.set_disabled_engines,
            "describe_engines": tts_manager.describe_engines,
            "get_engine_capabilities": tts_manager.get_engine_capabilities,
            "get_engine_api": lambda engine_id=None: tts_manager.get_engine_api(engine_id),
            "call_engine_api": lambda method_name, *args, engine_id=None, **kwargs: tts_manager.call_engine_api(
                method_name,
                *args,
                engine_id=engine_id,
                **kwargs,
            ),
        },
        "fonts": {
            "small": fontSmall,
            "default": font,
            "large": fontLarge,
        },
        "apps": {
            "all": apps,
            "by_name": apps_by_name,
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
        "FILES_DIR": FILES_DIR,
        "AUTOCOMPLETE_PATH": AUTOCOMPLETE_PATH,
    }
    
    # Provide the initialized user preferences to app context
    context["user_preferences"] = user_preferences
    
    # Set TTS engine based on user preferences
    preferred_engine = user_preferences.get_tts_engine()
    if tts_manager.set_engine(preferred_engine):
        print(f"[Main] TTS engine set to: {preferred_engine}")
    else:
        print(f"[Main] Failed to set TTS engine to: {preferred_engine}, using default")
    
    # Create and use the reusable AppManager
    from app_manager import AppManager
    app_manager = AppManager(APPS_DIR, OVERLAY_DIR, context)

    # Update context to include app_manager for other apps to use
    context["app_manager"] = app_manager

    sleep_controller = SleepController(
        display=disp,
        display_queue=display_queue,
        app_manager=app_manager,
        user_preferences=user_preferences,
        screen_size=(width, height),
        stop_music_cb=stop_music,
        stop_stream_cb=stop_audio_stream,
    )
    sleep_controller.set_idle_timeout(auto_sleep_seconds)
    context["sleep"] = {
        "controller": sleep_controller,
        "is_sleeping": lambda: sleep_controller.sleeping,
        "wake": sleep_controller.exit_sleep,
    }

    # Play startup audio/animation before any apps render
    play_startup_sequence()

    # Load all overlays
    overlay_count = app_manager.load_overlays(apps)
    print(f"[Main] Loaded {overlay_count} overlay apps")
    
    # Start all loaded overlays (unless disabled by user)
    for overlay_name in app_manager.overlay_apps:
        # Check if overlay is disabled in user preferences
        if user_preferences.is_overlay_disabled(overlay_name):
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

    def show_connecting():
        display_queue.put(("set_screen", "Connecting", "Looking for keyboard..."))
        display_queue.put(("draw_icon", searching_icon, 0, height - 8))

    def show_ready():
        display_queue.put(("clear_icon",))
        display_queue.put(("set_screen", "Ready", "Waiting for input..."))

    def show_disconnected():
        display_queue.put(("set_screen", "Disconnected", "Keyboard lost. Reconnecting..."))
        display_queue.put(("draw_icon", searching_icon, 0, height - 8))

    win_key_map = WIN_TO_LINUX_KEYCODE if IS_WINDOWS else None
    focus_check = getattr(disp, "is_window_focused", None)
    last_focus_state = True
    if user_preferences and hasattr(user_preferences, "get_keyboard_device_path"):
        preferred_keyboard_device = user_preferences.get_keyboard_device_path()
    else:
        preferred_keyboard_device = None

    keyboard_manager = KeyboardManager(
        is_windows=IS_WINDOWS,
        display=disp,
        win_keycode_map=win_key_map,
        queue_size=512,
        on_connect=show_ready,
        on_disconnect=show_disconnected,
        preferred_device=preferred_keyboard_device,
    )

    try:
        show_connecting()
        keyboard_manager.start()
        keyboard_manager.wait_until_ready(timeout=5.0)
        last_input_time = time.monotonic()

        poll_interval = 1.0 / 60.0
        while True:
            events = []
            first_event = keyboard_manager.get_event(timeout=poll_interval)
            if first_event is not None:
                events.append(first_event)
                while True:
                    next_event = keyboard_manager.get_event(timeout=0)
                    if next_event is None:
                        break
                    events.append(next_event)

            if not events:
                current_time = time.monotonic()
                if sleep_controller.should_sleep(last_input_time, current_time):
                    if sleep_controller.enter_sleep():
                        keys_pressed.clear()
                        last_input_time = current_time
                continue

            for event in events:
                if event.kind == "status":
                    if event.data == "connecting":
                        show_connecting()
                    elif event.data == "disconnected":
                        print("Keyboard disconnected. Reconnecting...", flush=True)
                        keys_pressed.clear()
                    elif event.data == "connected":
                        keys_pressed.clear()
                    continue

                keycode = event.keycode
                keystate = event.keystate

                if not keycode or keystate is None:
                    continue

                focused = focus_check() if focus_check else True
                if not focused:
                    if last_focus_state:
                        keys_pressed.clear()
                    last_focus_state = False
                    continue
                if not last_focus_state:
                    keys_pressed.clear()
                last_focus_state = True

                if sleep_controller.sleeping:
                    if keystate == KEY_DOWN and keycode == wake_keycode:
                        if sleep_controller.exit_sleep():
                            keys_pressed.clear()
                            last_input_time = time.monotonic()
                    elif keystate == KEY_UP and keycode == wake_keycode:
                        keys_pressed.discard(keycode)
                    continue

                if keystate == KEY_DOWN:
                    if keycode in keys_pressed:
                        continue
                    keys_pressed.add(keycode)
                    mapped_code = apply_shift_mapping(keycode, keys_pressed, shift_key_left, shift_key_right)
                    last_input_time = time.monotonic()
                    app_manager.distribute_event("onkeydown", mapped_code)
                elif keystate == KEY_UP:
                    if keycode in keys_pressed:
                        keys_pressed.remove(keycode)
                    mapped_code = apply_shift_mapping(keycode, keys_pressed, shift_key_left, shift_key_right)
                    last_input_time = time.monotonic()
                    app_manager.distribute_event("onkeyup", mapped_code)

            current_time = time.monotonic()
            if sleep_controller.should_sleep(last_input_time, current_time):
                if sleep_controller.enter_sleep():
                    keys_pressed.clear()
                    last_input_time = current_time
    except KeyboardInterrupt:
        print("Exiting on KeyboardInterrupt...")
    finally:
        if 'keyboard_manager' in locals():
            keyboard_manager.stop()
        # Stop all apps gracefully
        if 'app_manager' in locals():
            app_manager.stop_all_apps()
        
        # Clean up display
        disp.stop()  # Call our wrapper's stop method which calls cleanup()

if __name__ == "__main__":
    if not is_admin():
        print("⚠️ This script needs to be run as Administrator on Windows.")
    main()