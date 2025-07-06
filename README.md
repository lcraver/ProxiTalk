# ProxiTalk
This is the repo for ProxiTalk OS.

ProxiTalk is a custom operating system designed for the ProxiTalk "platform", which is a handheld gaming console and communication device.

# Apps Included

## ![Launcher Icon](assets/icons/settings.png) Launcher
Used to launch apps can be customized to the user's liking.

## ![Info Icon](apps/info/icon.png) Info
Test app for ProxiTalk for those that want a basic app to test with.

## ![ProxiTalk Icon](apps/proxi/icon.png) ProxiTalk
The main app for ProxiTalk, used for realtime TTS.

## ![Clock Icon](apps/clock/icon.png) Clock
A clock app for ProxiTalk.

## ![Hebi Icon](apps/hebi/icon.png) Hebi
The classic arcade game now on ProxiTalk~

## ![Tetra Icon](apps/tetra/icon.png) Tetra
The classic puzzle game now on ProxiTalk~

# Overlays Included

## ![Overlay Settings Icon](apps/overlay_settings/icon.png) Settings
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
        self.display_queue = context["display_queue"]  # Display commands
        
    def start(self):
        """Called when the app starts"""
        # Set a simple text screen
        self.display_queue.put(("set_screen", "My App", "Hello, ProxiTalk!"))
        
    def update(self):
        """Called every frame (20fps/hz by default)"""
        # Update game logic, animations, etc.
        pass
        
    def onkeydown(self, keycode):
        """Handle key press events"""
        # Handle key press events if needed
        if keycode == "KEY_ESC":
            # Return to launcher
            self.context["app_manager"].swap_app_async(
                "your_app_name", "launcher", update_rate_hz=20.0, delay=0.1
            )
        elif keycode == "KEY_SPACE":
            self.display_queue.put(("set_screen", "My App", "Space pressed!"))
            
    def onkeyup(self, keycode):
        """Handle key release events"""
        # Handle key release events if needed
        pass
        
    def stop(self):
        """Called when the app stops"""
        # Cleanup state or io if needed 
        pass
```

### Advanced Graphics with PIL

For custom graphics, create PIL images and send them to the display:

```python
def draw_custom_screen(self):
    # Create a 128x64 monochrome image (the size of the ProxiTalk display)
    img = Image.new("1", (128, 64), 0)  # 0 = black background
    draw = ImageDraw.Draw(img)
    
    # Draw shapes
    draw.rectangle([10, 10, 50, 30], fill=1)  # White rectangle
    draw.ellipse([60, 20, 80, 40], outline=1)  # White circle outline
    
    # Draw text
    font = self.fonts["default"]
    draw.text((10, 45), "Hello World!", font=font, fill=1)
    
    # Send to display
    self.display_queue.put(("clear_base",))
    self.display_queue.put(("draw_base_image", img, 0, 0))
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

### Display Commands

Send commands to the display using `self.display_queue.put()`:

```python
# Simple text screen
self.display_queue.put(("set_screen", "Title", "Message text"))

# Clear the display
self.display_queue.put(("clear_base",))

# Draw a PIL image at position (x, y)
self.display_queue.put(("draw_base_image", img, x, y))

# Draw text directly
self.display_queue.put(("draw_text", x, y, "text", font, fill))
```

### Audio and TTS

```python
# Play sound effects (place audio files in your app directory)
self.play_sfx(self.path + "sound.wav")
# Play background music (looped)
self.play_music(self.path + "music.wav", loop=True)

# Text-to-speech
# The background=True option allows TTS to run without drawing to the screen
self.run_tts("Hello, this will be spoken!", background=True)
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
        self.display_queue = context["display_queue"]
        self.play_sfx = context["audio"]["play_sfx"]
        self.path = context["app_path"]
        
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
        img = Image.new("1", (128, 64), 0)
        draw = ImageDraw.Draw(img)
        
        # Draw player
        draw.rectangle([self.player_x-2, self.player_y-2, 
                       self.player_x+2, self.player_y+2], fill=1)
        
        # Draw score
        font = self.context["fonts"]["small"]
        draw.text((5, 5), f"Score: {self.score}", font=font, fill=1)
        
        self.display_queue.put(("clear_base",))
        self.display_queue.put(("draw_base_image", img, 0, 0))
        
    def onkeydown(self, keycode):
        if keycode == "KEY_LEFT" and self.player_x > 5:
            self.player_x -= 5
            self.needs_redraw = True
        elif keycode == "KEY_RIGHT" and self.player_x < 123:
            self.player_x += 5
            self.needs_redraw = True
        elif keycode == "KEY_UP" and self.player_y > 5:
            self.player_y -= 5
            self.needs_redraw = True
        elif keycode == "KEY_DOWN" and self.player_y < 59:
            self.player_y += 5
            self.needs_redraw = True
        elif keycode == "KEY_ESC":
            self.context["app_manager"].swap_app_async(
                "your_game", "launcher", update_rate_hz=20.0, delay=0.1
            )
```

### Adding Your App to the Launcher

After creating your app, it will automatically be discovered by the ProxiTalk system. Make sure to include appropriate icon files.

### Debugging Tips

- Use `print()` statements for console debugging
- Check the console output when running `python proxitalk.py`
- The emulator window shows the actual display output
- Use try/catch blocks around PIL operations to handle errors gracefully