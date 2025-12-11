# ProxiTalk
This is the repo for ProxiTalk OS.

ProxiTalk is a custom operating system designed for the ProxiTalk "platform", which is a handheld gaming console and communication device.

# Apps Included

## System & Communication

### Launcher
Browse, favorite, and launch every installed experience on the device.

### ![Proxi Icon](apps/proxi/icon.png) Proxi
Flagship TTS communicator for typing and speaking phrases fast.

### ![App Settings Icon](apps/_Settings/app_settings/icon.png) App Settings
Toggle app visibility and tweak how entries appear in the launcher.

### ![TTS Settings Icon](apps/_Settings/tts_settings/icon.png) TTS Settings
Pick which engines are active, adjust voices, and tune speech defaults.

### ![App Reboot Icon](apps/_Settings/reboot/icon.png) App Reboot
Soft-restart the runtime when you need a quick clean slate.

### ![Discourse Chat Icon](apps/_Internet/discourse_chat/icon.png) Discourse Chat
Chat with The Garden forums directly from your ProxiTalk handheld.

### ![Browser Icon](apps/_Internet/pt_browser/icon.png) ProxiTalk Browser
Minimalist browser tailored to the 128x64 screen for quick lookups.

## Utilities & Creative Tools

### ![Calendar Icon](apps/_Utils/calendar/icon.png) Calendar [WIP]
Proof-of-concept monthly calendar for jotting down upcoming events.

### ![Clock Icon](apps/_Utils/clock/icon.png) Clock
Displays current time/date and offers simple timer capability.

### ![Code Editor Icon](apps/_Utils/code_editor/icon.png) Code Editor
Lightweight editor with syntax highlighting and basic file tools.

### ![Gallery Icon](apps/_Utils/gallery/icon.png) Gallery
Browse monochrome previews of locally stored images.

### ![Git Sync Icon](apps/_Utils/git_sync/icon.png) Git Sync
Check the public repo for updates and sync apps/overlays in place.

### ![Video Player Icon](apps/_Utils/video_player/icon.png) Video Player
Drop in an MP4 and play it back on the ProxiTalk display.

## Games

### ![Doom Clone Icon](apps/_Games/doom_clone/icon.png) Doom Clone
Retro raycasting FPS demo lovingly inspired by DOOM.

### ![Hebi Icon](apps/_Games/hebi/icon.png) Hebi
Classic snake gameplay built for the ProxiTalk controls.

### ![Tetra Icon](apps/_Games/tetra/icon.png) Tetra
Drop-block puzzle classic adapted to the 1-bit panel.

# Overlays Included

## Life Countdown
A life countdown overlay that displays approximate seconds remaining for you to live. Can be turned off in app settings if you want less existential dread.

## Settings
Configure screen brightness, volume, and more without leaving the app you're in.

---

# Developer Documentation

## Getting Started

### Prerequisites
- Python 3.7+
- PIL (Pillow) for image processing
- pygame (for Windows emulation)
- keyboard (for Windows input handling)

### Running ProxiTalk
```bash
python proxitalk.py
```

On Windows, this will start the emulated display. On Linux, it will run on actual hardware.

## Creating Custom Apps

### App Structure
Every ProxiTalk app follows this structure:
```
apps/
└── your_app_name/
    ├── main.py           # Required: Contains the App class
    ├── metadata.json     # Required: App metadata
    ├── icon.png          # Required: App icon (26x26 recommended)
    ├── icon_selected.png # Required: Selected state icon
    └── assets/           # Optional: App-specific assets
```

### Basic App Template

Create `apps/your_app_name/main.py`:

```python
from interfaces import AppBase
from PIL import Image, ImageDraw

class App(AppBase):
    def __init__(self, context):
        """Initialize the app with context"""
        super().__init__(context)
        
    def start(self):
        """Called when the app starts"""
        # Set a simple text screen using the built-in method
        self.set_screen("My App", "Hello, ProxiTalk!")
        
    def update(self):
        """Called every frame (20fps/hz by default)"""
        # Update game logic, animations, etc.
        pass
        
    def onkeydown(self, keycode):
        """Handle key press events"""
        if keycode == "KEY_ESC":
            # Return to launcher
            self.context["app_manager"].swap_app_async(
                "your_app_name", "launcher", update_rate_hz=20.0, delay=0.1
            )
        elif keycode == "KEY_SPACE":
            self.set_screen("My App", "Space pressed!")
            
    def onkeyup(self, keycode):
        """Handle key release events"""
        pass
        
    def stop(self):
        """Called when the app stops"""
        # Cleanup state or resources if needed 
        pass
```

### Drawing Methods

ProxiTalk provides several built-in methods for displaying content:

#### High-Level Screen Methods

```python
# Simple text screen with title and body
self.set_screen("Title", "Body text content")

self.set_screen_with_cursor("Editor", "Type here: [highlighted text]")

# Temporary message screen
self.show_message("Success", "File saved!", duration=2)

# Error screen
self.show_error("File not found")

# Loading screen
self.show_loading("Processing...")
```

#### Low-Level Drawing with Context Methods

For custom graphics, you can use the context drawing methods:

```python
def draw_custom_screen(self):
    # Create a 128x64 monochrome image (the size of the ProxiTalk display)
    img = Image.new("1", (128, 64), 0)  # 0 = black background
    draw = ImageDraw.Draw(img)
    
    # Draw shapes
    draw.rectangle([10, 10, 50, 30], fill=1)  # White rectangle
    draw.ellipse([60, 20, 80, 40], outline=1)  # White circle outline
    
    # Draw text on the image
    font = self.context["fonts"]["small"]
    draw.text((10, 45), "Hello World!", font=font, fill=1)
    
    # Clear display and draw the image
    self.context["drawing"]["clear_screen"]()
    self.context["drawing"]["draw_image"](img, 0, 0)
```

### Key Codes

While you can use almost all standard key codes, here are some commonly used ones:
- `KEY_ESC` - Escape key
- `KEY_SPACE` - Spacebar
- `KEY_UP`, `KEY_DOWN`, `KEY_LEFT`, `KEY_RIGHT` - Arrow keys
- `KEY_W`, `KEY_A`, `KEY_S`, `KEY_D` - WASD keys
- `KEY_ENTER` - Enter key
- `KEY_P` - P key (commonly used for pause)
- `KEY_R` - R key (commonly used for restart)

### Drawing Commands

Use the context drawing methods for efficient rendering:

#### Basic Drawing Commands
```python
# Clear the display
self.context["drawing"]["clear_screen"]()

# Draw a PIL image at position (x, y)
self.context["drawing"]["draw_image"](img, x, y)

# Draw text directly
self.context["drawing"]["draw_text"]("text", x, y, font)
# Or with custom fill color
self.context["drawing"]["draw_text"]("text", x, y, font, fill=255)

# Clear a specific area
self.context["drawing"]["clear_area"](x, y, width, height)

# Draw a filled area
self.context["drawing"]["draw_area"](x, y, width, height, fill=255)
```

#### Overlay Commands (for overlays and temporary content)
```python
# Draw on the overlay layer (appears on top of apps)
self.context["drawing"]["draw_overlay_text"]("text", x, y, font)
self.context["drawing"]["draw_overlay_image"](img, x, y)
self.context["drawing"]["clear_overlay_area"](x, y, width, height)
self.context["drawing"]["draw_overlay_area"](x, y, width, height, fill=255)
```

#### Performance Optimization
```python
# Batch multiple drawing operations for better performance
self.context["drawing"]["begin_batch"]()
self.context["drawing"]["draw_text"]("Player 1", 10, 10)
self.context["drawing"]["draw_text"]("Score: 100", 10, 20)
self.context["drawing"]["draw_area"](50, 50, 10, 10, fill=255)
self.context["drawing"]["end_batch"]()  # All drawing happens at once
```

#### Text Features
The built-in `set_screen()` method supports:
- Automatic text wrapping
- Highlighted text using `[brackets]`
- Proper spacing and layout

### Audio and TTS

```python
# Play sound effects (place audio files in your app directory)
self.context["audio"]["play_sfx"](self.context["app_path"] + "sound.wav")

# Play background music (looped)
self.context["audio"]["play_music"](self.context["app_path"] + "music.wav", loop=True)

# Text-to-speech
self.context["tts"]["run"]("Hello, this will be spoken!", background=True)
```

### App Metadata

Create `apps/your_app_name/metadata.json`:

```json
{
  "name": "My Custom App",
  "version": "1.0",
  "description": "A description of what your app does",
  "author": "Your Name",
  "type": "app"
}
```

For overlay apps (run in background):
```json
{
  "name": "My Overlay",
  "version": "1.0",
  "description": "A description of what your overlay does",
  "author": "Your Name",
  "type": "overlay"
}
```

### Example: Simple Game Template

```python
from interfaces import AppBase
from PIL import Image, ImageDraw
import random

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        
        # Game state
        self.player_x = 64
        self.player_y = 32
        self.score = 0
        self.needs_redraw = True
        
    def start(self):
        self.needs_redraw = True
        
    def update(self):
        if self.needs_redraw:
            self.draw_game()
            self.needs_redraw = False
            
    def draw_game(self):
        # Use batching for better performance
        self.context["drawing"]["begin_batch"]()
        
        # Clear screen
        self.context["drawing"]["clear_screen"]()
        
        # Draw player as a filled rectangle
        self.context["drawing"]["draw_area"](
            self.player_x-2, self.player_y-2, 4, 4, fill=255
        )
        
        # Draw score
        font = self.context["fonts"]["small"]
        self.context["drawing"]["draw_text"](
            f"Score: {self.score}", 5, 5, font
        )
        
        # Execute all drawing at once
        self.context["drawing"]["end_batch"]()
        
    def onkeydown(self, keycode):
        moved = False
        
        if keycode == "KEY_LEFT" and self.player_x > 5:
            self.player_x -= 5
            moved = True
        elif keycode == "KEY_RIGHT" and self.player_x < 123:
            self.player_x += 5
            moved = True
        elif keycode == "KEY_UP" and self.player_y > 5:
            self.player_y -= 5
            moved = True
        elif keycode == "KEY_DOWN" and self.player_y < 59:
            self.player_y += 5
            moved = True
        elif keycode == "KEY_ESC":
            self.context["app_manager"].swap_app_async(
                "your_game", "launcher", update_rate_hz=20.0, delay=0.1
            )
            
        if moved:
            self.needs_redraw = True
```

### Adding Your App to the Launcher

After creating your app, it will automatically be discovered by the ProxiTalk system. Make sure to include appropriate icon files.

### Debugging Tips

- Use `print()` statements for console debugging
- Check the console output when running `python proxitalk.py`
- The emulator window shows the actual display output
- Use try/catch blocks around PIL operations to handle errors gracefully

### Debug Overlay for Performance Optimization

ProxiTalk includes a built-in debug overlay system to help developers optimize their drawing operations and understand how the display system works:

#### Enabling Debug Overlay

**In the emulator (Windows):**
- Press `F1` while the emulator window is focused to toggle the debug overlay on/off
- When enabled, you'll see red rectangles highlighting areas of the screen that are being updated
- The console will show: `[Debug] Region overlay: ON` or `[Debug] Region overlay: OFF`

#### How the Debug Overlay Works

- **Red rectangles** appear whenever a drawing operation updates part of the screen
- Each rectangle shows the **exact region** that was modified by a drawing call
- Rectangles **fade out over time** (about 5 frames) to show the update sequence
- **Semi-transparent** overlay allows you to see both the content and the update regions

#### Using Debug Overlay for Optimization

```python
# Example: Inefficient drawing (many small updates)
def bad_draw_example(self):
    for i in range(10):
        self.context["drawing"]["draw_text"](f"Line {i}", 10, i*10, font)
    # Debug overlay will show 10 separate red rectangles

# Example: Efficient drawing (batched updates)
def good_draw_example(self):
    self.context["drawing"]["begin_batch"]()
    for i in range(10):
        self.context["drawing"]["draw_text"](f"Line {i}", 10, i*10, font)
    self.context["drawing"]["end_batch"]()
    # Debug overlay will show 1 red rectangle covering the entire area
```

#### What to Look For

- **Too many small rectangles**: Consider using `begin_batch()` and `end_batch()`
- **Large rectangles for small changes**: You might be clearing/redrawing too much
- **Overlapping rectangles**: Multiple drawing calls affecting the same area
- **Constant flickering**: Indicates unnecessary redraws every frame

#### Performance Tips Based on Debug Overlay

1. **Batch related operations**: Group drawing calls that happen together
2. **Minimize cleared areas**: Only clear the specific regions that changed
3. **Use dirty flags**: Only redraw when something actually changed
4. **Separate static/dynamic content**: Use overlay layer for frequently changing elements

The debug overlay only works in the Windows emulator and helps identify inefficient drawing patterns that could impact performance on actual hardware.