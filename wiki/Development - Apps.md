# ProxiTalk App Development Guide

This guide covers how to develop applications for ProxiTalk and use the Windows emulator for testing your apps.

## Windows Emulator Setup

The ProxiTalk Windows emulator provides a pixel-perfect simulation of the target hardware display (128x64 OLED) with 4x scaling for development.

### Running the Emulator

```bash
# Navigate to ProxiTalk directory
cd ProxiTalk

# Run ProxiTalk emulator
python proxitalk.py
```

### Emulator Features

- **Display Emulation**: 128x64 pixel OLED display scaled 4x (512x256 window)
- **Input Simulation**: Full keyboard mapping to simulate hardware buttons
- **Audio Playback**: Uses pygame mixer for sound effects and TTS
- **Real-time Testing**: Hot-reload capabilities for rapid development
- **Debug Drawing Overlay**: Press `F1` to toggle region update visualization (or edit the `proxitalk.py` file to enable by default)

## App Structure

Every ProxiTalk app follows a standardized directory structure. The following setup is required for your app to be recognized / work in the ProxiTalk system:

```
apps/
└── your_app_name/
    ├── main.py           # Contains the App class
    ├── metadata.json     # App metadata
    ├── icon.png          # App icon (26x26 recommended)
    ├── icon_selected.png # Selected app icon (26x26 recommended)
```

### Required Files

#### `main.py`
Contains the main App class that inherits from `AppBase`:

```python
from interfaces import AppBase
from PIL import Image, ImageDraw

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        # Initialize your app here
        
    def start(self):
        # Called when app starts
        pass
        
    def update(self):
        # Called every frame (20 FPS)
        pass
        
    def onkeydown(self, keycode):
        # Handle key press events
        pass
        
    def onkeyup(self, keycode):
        # Handle key release events
        pass
        
    def stop(self):
        # Called when app stops
        pass
```

#### `metadata.json`
Contains app information:

```json
{
  "name": "Your App Name",
  "version": "1.0",
  "description": "Brief description of your app",
  "author": "Your Name",
  "category": "utility"
}
```

#### Icon Files
- `icon.png`: 26x26 pixel icon (normal state)
- `icon_selected.png`: 26x26 pixel icon (selected state)

Both icons should be monochrome (black and white) for consistency with the OLED display.

## Creating Your First App

Let's create a simple "Hello World" app:

### Step 1: Create App Directory

```bash
mkdir apps/hello_world
cd apps/hello_world
```

### Step 2: Create `metadata.json`

```json
{
  "name": "Hello World",
  "version": "1.0",
  "description": "A simple hello world app", // if you want
  "author": "Your Name", // if you want
}
```

### Step 3: Create `main.py`

```python
from interfaces import AppBase
from PIL import Image, ImageDraw
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.message = "Hello, ProxiTalk!"
        self.counter = 0
        self.drawing = context["drawing"]
        self.width = context["screen_width"]
        self.height = context["screen_height"]
        self.font_large = context["fonts"]["large"]
        self.font_small = context["fonts"]["small"]
        self.get_text_size = context["get_text_size"]
        
    def start(self):
        """Called when the app starts"""
        print("[Hello World] App started!")
        self.draw_screen()
        
    def update(self):
        """Called every frame (20 FPS)"""
        self.counter += 1
        
        # Update every 60 frames (3 seconds at 20 FPS)
        if self.counter >= 60:
            self.counter = 0
            current_time = time.strftime("%H:%M:%S")
            self.message = f"Time: {current_time}"
            self.draw_screen()
            
    def draw_screen(self):
        """Draw the app screen using ProxiTalk's drawing API"""
        # Clear the screen
        self.drawing["clear_screen"]()
        
        # Draw title
        title = "Hello World"
        title_width, title_height = self.get_text_size(title, self.font_large)
        title_x = (self.width - title_width) // 2
        self.drawing["draw_text"](title, title_x, 8, self.font_large)
        
        # Draw message
        msg_width, msg_height = self.get_text_size(self.message, self.font_small)
        msg_x = (self.width - msg_width) // 2
        msg_y = 28
        self.drawing["draw_text"](self.message, msg_x, msg_y, self.font_small)
        
        # Draw instructions
        instructions = "Press ENTER or ESC"
        inst_width, inst_height = self.get_text_size(instructions, self.font_small)
        inst_x = (self.width - inst_width) // 2
        self.drawing["draw_text"](instructions, inst_x, 48, self.font_small)
            
    def onkeydown(self, keycode):
        """Handle key press events"""
        if keycode == "KEY_ENTER":
            self.message = "Button pressed!"
            self.draw_screen()
        elif keycode == "KEY_ESC":
            # Return to launcher
            self.context["app_manager"].launch_app("launcher")
            
    def stop(self):
        """Called when the app stops"""
        print("[Hello World] App stopped!")
```

### Step 4: Create Icons

Create simple 26x26 pixel black and white icons:
- `icon.png`: Normal state icon
- `icon_selected.png`: Selected state icon (can be inverted or highlighted)

### Step 5: Test Your App

```bash
# Navigate to ProxiTalk root directory
cd ../ # if you are in the app directory

# Run the emulator
python proxitalk.py

# Navigate to your app in the launcher and press Enter to launch it
```

## App Development API

### Context Object

The `context` parameter provides access to ProxiTalk's core functionality:

```python
def __init__(self, context):
    # Display properties
    self.width = context["screen_width"]      # 128 pixels
    self.height = context["screen_height"]    # 64 pixels
    
    # Fonts
    self.font_small = context["fonts"]["small"]
    self.font_large = context["fonts"]["large"]
    
    # Audio
    self.play_sfx = context["audio"]["play_sfx"]
    self.play_tts = context["audio"]["play_tts"]
    
    # System
    self.app_manager = context["app_manager"]
    self.drawing = context["drawing"]
    self.user_prefs = context["user_preferences"]
    
    # Utilities
    self.get_text_size = context["get_text_size"]
    self.app_path = context["app_path"]
```

### Display Methods

#### `set_screen(title, text)`
Quick method to display text with a title:

```python
def start(self):
    self.set_screen("My App", "Welcome to my app!")
```

#### Modern Drawing API
Use the `context["drawing"]` methods for advanced graphics:

```python
def update(self):
    # Clear the screen
    self.drawing["clear_screen"]()
    
    # Draw text
    self.drawing["draw_text"](text, x, y, font)
    
    # Draw an image
    self.drawing["draw_image"](image, x, y)
    
    # Draw filled rectangle/area
    self.drawing["draw_area"](x, y, width, height, fill=255)
    
    # Clear specific area
    self.drawing["clear_area"](x, y, width, height)
```

#### Overlay Layer (for temporary content)
Use overlay methods for content that changes frequently:

```python
def draw_animation(self):
    # Draw on overlay layer (for cursors, animations, etc.)
    self.drawing["draw_overlay_text"](text, x, y, font)
    self.drawing["draw_overlay_image"](image, x, y)
    
    # Clear overlay areas
    self.drawing["clear_overlay_area"](x, y, width, height)
```

#### Performance Optimization with Batching
For multiple drawing operations, use batching:

```python
def draw_complex_scene(self):
    # Start batching operations
    self.drawing["begin_batch"]()
    
    # Multiple drawing operations
    self.drawing["draw_text"]("Line 1", 10, 10, self.font_small)
    self.drawing["draw_text"]("Line 2", 10, 20, self.font_small)
    self.drawing["draw_area"](50, 50, 20, 10, fill=255)
    
    # Execute all operations at once
    self.drawing["end_batch"]()
```

### Audio Methods

#### Sound Effects
```python
def play_sound_effect(self):
    # Play a WAV file from your app's directory
    sound_path = f"{self.app_path}/assets/sounds/beep.wav"
    self.play_sfx(sound_path)
```

#### Text-to-Speech
```python
def speak_text(self):
    # Use Piper TTS to speak text
    self.play_tts("Hello from my app!")
```

### App Management

#### Launch Other Apps
```python
def switch_to_launcher(self):
    self.app_manager.launch_app("launcher")

def launch_settings(self):
    self.app_manager.launch_app("app_settings")
```

## Input Handling

### Key Codes

ProxiTalk uses Linux-style key codes. Common ones include:

```python
# Navigation
"KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT"
"KEY_W", "KEY_S", "KEY_A", "KEY_D"
"KEY_ENTER"    # Confirm/Select
"KEY_ESC"      # Back/Cancel
```

### Input Examples

```python
def onkeydown(self, keycode):
    if keycode == "KEY_UP":
        self.selection -= 1
    elif keycode == "KEY_DOWN":
        self.selection += 1
    elif keycode == "KEY_ENTER":
        self.confirm_selection()
    elif keycode == "KEY_ESC":
        self.go_back()
    elif keycode.startswith("KEY_") and len(keycode) == 5:
        # Handle text input
        letter = keycode[-1].lower()
        self.text_input += letter
```

## Graphics and Display

### Display Specifications

- **Resolution**: 128x64 pixels
- **Color Depth**: 1-bit (monochrome)
- **Refresh Rate**: 20 FPS (this is optimistic the display typically will max out at 10-15 FPS)
- **Color Values**: 0 (black/off) or 255 (white/on)

### Drawing with PIL

ProxiTalk uses Python Imaging Library (PIL) for graphics:

```python
from PIL import Image, ImageDraw

def create_custom_screen(self):
    # Create a new image
    image = Image.new('1', (self.width, self.height), 0)  # Black background
    draw = ImageDraw.Draw(image)
    
    # Draw shapes
    draw.rectangle((10, 10, 50, 30), fill=255)  # White rectangle
    draw.ellipse((60, 10, 100, 50), outline=255)  # White circle outline
    
    # Draw text
    draw.text((10, 40), "Hello!", font=self.font_small, fill=255)
    
    # Display the image
    self.drawing["draw_image"](image, 0, 0)
```

### Animation

```python
class AnimatedApp(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.frame = 0
        self.x_pos = 0
        self.drawing = context["drawing"]
        
    def update(self):
        self.frame += 1
        
        # Animate every 5 frames
        if self.frame % 5 == 0:
            self.x_pos = (self.x_pos + 2) % self.width
            
            # Clear and redraw
            self.drawing["clear_screen"]()
            image = Image.new('1', (self.width, self.height), 0)
            draw = ImageDraw.Draw(image)
            draw.rectangle((self.x_pos, 30, self.x_pos + 10, 40), fill=255)
            self.drawing["draw_image"](image, 0, 0)
```

### Text Wrapping and Formatting

The `set_screen` method automatically handles text wrapping, but you can also implement custom text layouts:

```python
def wrap_text(self, text, font, max_width):
    """Wrap text to fit within max_width pixels"""
    words = text.split(' ')
    lines = []
    current_line = ""
    
    for word in words:
        test_line = current_line + (" " if current_line else "") + word
        width, _ = self.get_text_size(test_line, font)
        
        if width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return lines
```

## Audio Integration

### Sound Effects

Store audio files in your app's `assets/sounds/` directory:

```python
def play_menu_sound(self):
    sound_path = f"{self.app_path}/assets/sounds/menu_beep.wav"
    self.play_sfx(sound_path)

def play_success_sound(self):
    sound_path = f"{self.app_path}/assets/sounds/success.wav"
    self.play_sfx(sound_path)
```

### Text-to-Speech

```python
def announce_score(self, score):
    self.play_tts(f"Your score is {score} points")

def provide_instructions(self):
    self.play_tts("Use arrow keys to navigate and enter to select")
```

## Testing with the Emulator

### Development Workflow

1. **Start the Emulator**:
   ```bash
   python proxitalk.py
   ```

2. **Navigate to Your App**: Use arrow keys to find your app in the launcher

3. **Launch Your App**: Press Enter to launch

4. **Test Functionality**: Test all features and input scenarios

5. **Debug Issues**: Use print statements and the debug overlay (F1)

### Hot Reload

To test changes without restarting:

1. Make changes to your app code
2. In the emulator, press Escape to return to launcher
3. Launch your app again to see changes

### Performance Testing

Monitor your app's performance:

```python
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.last_update_time = time.time()
        
    def update(self):
        current_time = time.time()
        delta_time = current_time - self.last_update_time
        
        # Log if frame takes too long (should be ~50ms for 20 FPS)
        if delta_time > 0.1:  # 100ms
            print(f"[Performance] Slow frame: {delta_time:.3f}s")
            
        self.last_update_time = current_time
        
        # Your update logic here
```

## Debugging and Troubleshooting

### Common Issues

#### App Not Appearing in Launcher
- Check that `metadata.json` exists and is valid JSON
- Ensure `main.py` contains a class named `App`
- Verify the app directory is in the `apps/` folder

#### Display Issues
- Make sure you're using 1-bit images (mode='1')
- Check that coordinates are within screen bounds (0-127, 0-63)
- Verify color values are 0 or 255

#### Audio Not Playing
- Check that audio files are in WAV format
- Verify file paths are correct
- Ensure pygame mixer is initialized (happens automatically)

#### Input Not Working
- Print keycode values to debug: `print(f"Key pressed: {keycode}")`
- Check key code format (e.g., "KEY_A", not "a")
- Verify onkeydown method is implemented

### Debug Techniques

#### Logging
```python
class App(AppBase):
    def onkeydown(self, keycode):
        print(f"Key pressed: {keycode}")
```

#### Visual Debugging
```python
def debug_draw_bounds(self):
    """Draw debug rectangles to visualize UI elements"""
    image = Image.new('1', (self.width, self.height), 0)
    draw = ImageDraw.Draw(image)
    
    # Draw button bounds
    for i, button in enumerate(self.buttons):
        x, y, w, h = button['bounds']
        draw.rectangle((x, y, x+w, y+h), outline=255)
        
    self.drawing["draw_overlay_image"](image, 0, 0)
```

#### State Monitoring
```python
def update(self):
    # Print state every 60 frames (3 seconds)
    if self.frame % 60 == 0:
        print(f"App State: mode={self.mode}, selection={self.selection}")
```

### Error Handling

```python
def safe_update(self):
    try:
        self.update_game_logic()
    except Exception as e:
        print(f"[Error] Update failed: {e}")
        self.set_screen("Error", f"An error occurred: {str(e)}")

def safe_file_load(self, filename):
    try:
        with open(filename, 'r') as f:
            return f.read()
    except FileNotFoundError:
        print(f"[Warning] File not found: {filename}")
        return None
    except Exception as e:
        print(f"[Error] Failed to load {filename}: {e}")
        return None
```