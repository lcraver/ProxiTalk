from unicodedata import name
from interfaces import AppBase
import bisect
import os
from config.keymap import key_map, shift_key_map

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.draw = context["drawing"]  # New region-based drawing system
        self.context = context
        self.words = self.load_autocomplete_words(context["AUTOCOMPLETE_PATH"])
        self.autocomplete_words = self.load_autocomplete_words(context["AUTOCOMPLETE_PATH"])
        self.autocomplete_words.sort()
        self.currentline = ""
        self.current_suggestion = ""
        
        # UI constants
        self.width = context["screen_width"] 
        self.height = context["screen_height"]
        self.padding = 2
        
        # Cursor state
        self.cursor_visible = False
        self.cursor_x = self.padding
        self.cursor_y = 8
        self.cursor_blink_timer = 0
        self.cursor_blink_interval = 0.5  # Blink every 500ms
        self._in_input_mode = False  # Track if we're actively inputting text
        
        print("[Proxi] Initialized with hardware optimizations")
        print("[Proxi] - Region-based drawing for minimal display transfers")
        print("[Proxi] - Batching enabled for smooth updates on real hardware")
        
    def load_autocomplete_words(self, filepath):
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

    def parse_text_segments(self, text):
        """Parse text to identify highlighted segments in [brackets]"""
        import re
        segments = []
        pattern = r'\[([^\]]+)\]'
        last_end = 0
        
        for match in re.finditer(pattern, text):
            # Add regular text before the highlight
            if match.start() > last_end:
                segments.append({
                    'text': text[last_end:match.start()],
                    'highlighted': False
                })
            
            # Add highlighted text
            segments.append({
                'text': match.group(1),
                'highlighted': True
            })
            
            last_end = match.end()
        
        # Add remaining regular text
        if last_end < len(text):
            segments.append({
                'text': text[last_end:],
                'highlighted': False
            })
        
        return segments

    def draw_highlighted_text(self, segments, x, y, font):
        """Draw text with highlighted segments (white background for bracketed text)"""
        current_x = x
        
        for segment in segments:
            if not segment['text']:
                continue
                
            text_width, text_height = self.context["get_text_size"](segment['text'], font)
            
            if segment['highlighted']:
                # Create white background with black text (inverted)
                bg_width = text_width + 2  # Small padding
                bg_height = text_height + 2
                
                # Draw white background
                self.draw["draw_area"](current_x, y - 1, bg_width, bg_height, 255)
                
                # Draw black text on white background
                self.draw["draw_text"](segment['text'], current_x + 1, y, font, 0)
                
                current_x += bg_width
            else:
                # Regular white text on black background
                self.draw["draw_text"](segment['text'], current_x, y, font, 255)
                current_x += text_width
        
        return current_x

    def draw_cursor(self, x, y):
        """Draw a simple cursor at the specified position on the overlay layer"""
        if self.cursor_visible:
            # Draw a simple vertical line cursor (1 pixel wide, 5 pixels tall) on overlay
            cursor_width = 1
            cursor_height = 6
            self.draw["draw_overlay_area"](x, y-1, cursor_width, cursor_height, 255)

    def draw_help_text(self, content_y, wrapped_lines, font_small, line_height, has_suggestion, suggestion_y=None):
        """Draw help text at the bottom of the screen"""
        if has_suggestion:
            help_text = "ALT: Accept  ENTER: Speak"
            help_y = max(content_y + len(wrapped_lines) * line_height + 8, suggestion_y + 8)
        else:
            help_text = "ENTER: Speak"
            help_y = content_y + len(wrapped_lines) * line_height + 8
        
        if help_y + line_height <= self.height - 2:
            help_width = self.context["get_text_size"](help_text, font_small)[0]
            help_x = (self.width - help_width) // 2
            self.draw["draw_text"](help_text, help_x, help_y, font_small, 255)

    def get_autocomplete_suggestion(self, current_text):
        if not current_text or current_text.endswith(' '):
            return ""
        last_word = current_text.split(' ')[-1].lower()
        if not last_word:  # Extra safety check
            return ""
        i = bisect.bisect_left(self.autocomplete_words, last_word)
        while i < len(self.autocomplete_words) and self.autocomplete_words[i].startswith(last_word):
            candidate = self.autocomplete_words[i]
            suggestion = candidate[len(last_word):]
            if suggestion:  # Make sure we have a non-empty suggestion
                return suggestion
            i += 1
        return ""

    def draw_interface(self, title, content):
        """Draw the interface using region-based updates with hardware optimization"""
        # Use batching for optimal hardware performance
        self.draw["begin_batch"]()
        
        try:
            # Clear screen and overlay layer
            self.draw["clear_screen"]()
            self.draw["clear_overlay_area"](0, 0, self.width, self.height)  # Clear overlay layer
            
            # Draw title section with white background
            font_small = self.context["fonts"]["small"]
            title_height = 6
            self.draw["draw_area"](0, 0, self.width, title_height, 255)  # White background
            
            # Center the title
            title_width = self.context["get_text_size"](title, font_small)[0]
            title_x = (self.width - title_width) // 2
            self.draw["draw_text"](title, title_x, 1, font_small, 0)  # Black text on white
            
            # Draw content area
            content_y = title_height + 2
            
            if title == "Input":
                # Input mode - show current text with autocomplete suggestion
                if self.currentline or self._in_input_mode:
                    # Wrap the current text to fit within screen width
                    available_width = self.width - self.padding * 2
                    wrapped_lines = self.wrap_text(self.currentline, font_small, available_width)
                    line_height = 6
                    
                    # Draw each line of wrapped text
                    for i, line in enumerate(wrapped_lines):
                        line_y = content_y + i * line_height
                        if line_y + line_height > self.height - 8:  # Don't overflow
                            break
                        self.draw["draw_text"](line, self.padding, line_y, font_small, 255)
                    
                    # Calculate cursor position - it should be at the end of the last line
                    if wrapped_lines:
                        last_line = wrapped_lines[-1]
                        last_line_index = len(wrapped_lines) - 1
                        
                        # Calculate actual text width of the last line
                        if last_line:
                            from PIL import ImageDraw, Image
                            temp_img = Image.new("1", (1, 1))
                            temp_draw = ImageDraw.Draw(temp_img)
                            bbox = temp_draw.textbbox((0, 0), last_line, font=font_small)
                            actual_text_width = bbox[2] - bbox[0]
                            self.cursor_x = self.padding + actual_text_width
                        else:
                            self.cursor_x = self.padding
                        
                        self.cursor_y = content_y + last_line_index * line_height
                    else:
                        self.cursor_x = self.padding
                        self.cursor_y = content_y
                    
                    # Draw autocomplete suggestion if available
                    if self.current_suggestion and wrapped_lines:
                        last_line = wrapped_lines[-1]
                        last_line_y = content_y + (len(wrapped_lines) - 1) * line_height
                        
                        # Check if suggestion fits on the same line
                        suggestion_text = f"[{self.current_suggestion}]"
                        suggestion_width = self.context["get_text_size"](suggestion_text, font_small)[0]
                        
                        if self.cursor_x + suggestion_width + 2 <= self.width - self.padding:
                            # Fits on same line
                            suggestion_x = self.cursor_x + 1
                            suggestion_y = last_line_y
                        else:
                            # Move to next line
                            suggestion_x = self.padding
                            suggestion_y = last_line_y + line_height
                            if suggestion_y + line_height <= self.height - 8:  # Make sure it fits
                                pass  # Use the calculated position
                            else:
                                suggestion_y = last_line_y  # Keep on same line but may overflow
                        
                        segments = self.parse_text_segments(suggestion_text)
                        self.draw_highlighted_text(segments, suggestion_x, suggestion_y, font_small)
                        
                        # Draw help text below everything
                        self.draw_help_text(content_y, wrapped_lines, font_small, line_height, True, suggestion_y)
                    else:
                        # No suggestion available, but still show help text without TAB
                        self.draw_help_text(content_y, wrapped_lines, font_small, line_height, False)
                    
                    # Draw cursor at end of typed text
                    self.draw_cursor(self.cursor_x, self.cursor_y)
                else:
                    # Empty input - just show cursor at padding position
                    self.cursor_x = self.padding
                    self.cursor_y = content_y
                    self.draw_cursor(self.cursor_x, self.cursor_y)
                    
                    # Show help text even when no input
                    wrapped_lines = [""]  # Empty line for positioning
                    self.draw_help_text(content_y, wrapped_lines, font_small, 6, False)
            else:
                # Regular content display (like "Ready" message)
                lines = self.wrap_text(content, font_small, self.width - self.padding * 2)
                line_height = 6
                
                for i, line in enumerate(lines):
                    if i * line_height + content_y + line_height > self.height - 8:
                        break
                    
                    # Parse line for highlighted segments
                    segments = self.parse_text_segments(line)
                    if any(seg['highlighted'] for seg in segments):
                        self.draw_highlighted_text(segments, self.padding, content_y + i * line_height, font_small)
                    else:
                        self.draw["draw_text"](line, self.padding, content_y + i * line_height, font_small, 255)
                    
        finally:
            # Execute all drawing operations at once for hardware optimization
            self.draw["end_batch"]()
    
    def wrap_text(self, text, font, max_width):
        """Wrap text to fit within the specified width"""
        if not text:
            return [""]
            
        words = text.split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            text_width = self.context["get_text_size"](test_line, font)[0]
            
            if text_width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
            
        return lines if lines else [""]

    def update_input_display(self):
        """Update the input display with current text and suggestion"""
        self.current_suggestion = self.get_autocomplete_suggestion(self.currentline)
        self.draw_interface("Input", "")

    def start(self):
        print("[Proxi] Started")
        # Initialize cursor state
        import time
        self.current_suggestion = ""
        self.cursor_visible = True
        self.cursor_blink_timer = time.time()
        
        self.draw_interface("Ready", "Start typing to see suggestions. Press [ESC] to return to launcher.")

    def update(self):
        """Handle cursor blinking and periodic updates"""
        import time
        current_time = time.time()
        
        # Handle cursor blinking only when in input mode
        if current_time - self.cursor_blink_timer > self.cursor_blink_interval:
            self.cursor_visible = not self.cursor_visible
            self.cursor_blink_timer = current_time
            
            # Only redraw if we're in input mode (have text or explicitly in input mode)
            if self._in_input_mode or self.currentline:
                self.draw_interface("Input", "")
    
    def onkeyup(self, keycode):
        if keycode == 'KEY_ESC':
            self.draw_interface("Launcher", "Switching to Launcher...")
            self.context["app_manager"].swap_app_async("proxi", "launcher", update_rate_hz=20.0, delay=0.1)
        
        if keycode == 'KEY_TAB' or keycode == 'KEY_RIGHTALT' or keycode == 'KEY_LEFTALT':
            suggestion = self.get_autocomplete_suggestion(self.currentline)
            if suggestion:
                self.currentline += suggestion + ' '
            self.update_input_display()
            return

        char = key_map.get(keycode, None)
        if char is None:
            return

        if keycode == 'KEY_ENTER':
            old_line = self.currentline
            
            # Run TTS
            self.context["run_tts"](self.currentline, background=True)
            
            # Check if audio was cached (immediate) or generated
            cached_path = os.path.join(self.context["CACHE_DIR"], self.context["hash_text"](old_line) + ".raw")
            if os.path.exists(cached_path):
                self.currentline = ""
                self.current_suggestion = ""
                self._in_input_mode = False  # Exit input mode
                self.draw_interface("Ready", "Ready for new input...")
            else:
                self.update_input_display()
                
        elif keycode == 'KEY_BACKSPACE':
            self._in_input_mode = True  # Enter input mode
            self.currentline = self.currentline[:-1]
            self.update_input_display()
            
        else:
            self._in_input_mode = True  # Enter input mode
            self.currentline += char
            self.update_input_display()
    
    def stop(self):
        print("[Proxi] Stopped")
