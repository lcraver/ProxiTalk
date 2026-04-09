from unicodedata import name
from interfaces import AppBase
import bisect
import os
import threading
import time
import queue
from config.keymap import key_map, shift_key_map
from utils.japanese import detect_and_convert_romanji

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.draw = context["drawing"]  # New region-based drawing system
        self.current_engine = context["tts"]["get_engine"]
        self.context = context
        
        # Load both English and Japanese autocomplete words
        self.words = self.load_autocomplete_words(context["AUTOCOMPLETE_PATH"])
        self.autocomplete_words = self.load_autocomplete_words(context["AUTOCOMPLETE_PATH"])
        self.autocomplete_words.sort()
        
        # Load Japanese autocomplete words
        japanese_path = context["AUTOCOMPLETE_PATH"].replace("autocomplete_words.txt", "autocomplete_words_japanese.txt")
        self.japanese_autocomplete_words = self.load_autocomplete_words(japanese_path)
        self.japanese_autocomplete_words.sort()
        
        print(f"[Proxi] Loaded {len(self.autocomplete_words)} English autocomplete words")
        print(f"[Proxi] Loaded {len(self.japanese_autocomplete_words)} Japanese autocomplete words")
        
        self.currentline = ""
        self.current_suggestion = ""
        
        # Japanese romanji preview state
        self.romanji_preview = None
        self.is_japanese_detected = False
        
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
        
        # TTS state
        self.tts_active = False  # Track if TTS is playing
        self.tts_state = "idle"  # "idle", "speaking"
        self.tts_thread = None  # Track TTS thread
        self.tts_queue = queue.Queue()  # Queue for TTS requests
        self.tts_worker_running = False  # Track if worker thread is running
        
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

    def redraw_cursor_only(self):
        """Redraw only the cursor on the overlay layer without touching the base layer"""
        # Clear only the cursor area of the overlay layer
        cursor_width = 2  # Slightly wider to ensure we clear the old cursor
        cursor_height = 8  # Slightly taller to ensure we clear the old cursor
        self.draw["clear_overlay_area"](self.cursor_x - 1, self.cursor_y - 2, cursor_width, cursor_height)
        
        # Redraw cursor if visible
        self.draw_cursor(self.cursor_x, self.cursor_y)

    def draw_help_text(self, content_y, wrapped_lines, font_small, line_height, has_suggestion, suggestion_y=None):
        """Draw help text at the bottom of the screen, with romanji preview if applicable"""
        # Calculate the base help position
        if has_suggestion:
            help_text = "ALT: Accept  ENTER: Speak"
            help_y = max(content_y + len(wrapped_lines) * line_height + 8, suggestion_y + 8)
        else:
            help_text = "ENTER: Speak"
            help_y = content_y + len(wrapped_lines) * line_height + 8
        
        # Check if we have Japanese romanji preview to show
        romanji_y = help_y
        if self.is_japanese_detected and self.romanji_preview:
            # Show romanji preview above help text using default font with proper wrapping
            preview_text = f"{self.romanji_preview}"
            font_default = self.context["fonts"]["default"]  # Use default font for Japanese text
            
            # Calculate proper line height for the Japanese default font
            japanese_line_height = self.context["get_text_size"]("あ", font_default)[1] + 1  # Get height of Japanese character + spacing
            
            # Wrap the Japanese preview text just like normal text
            available_width = self.width - self.padding * 2
            wrapped_preview_lines = self.wrap_text(preview_text, font_default, available_width)
            
            # Check if preview fits on screen using proper Japanese line height
            preview_height_needed = len(wrapped_preview_lines) * japanese_line_height
            if help_y + preview_height_needed + line_height + 4 <= self.height - 2:
                # Draw each line of wrapped Japanese preview
                for i, preview_line in enumerate(wrapped_preview_lines):
                    preview_line_y = help_y + i * japanese_line_height
                    # Draw inverted text (white background, black text) for Japanese preview
                    self.draw["draw_text_inverted"](preview_line, self.padding, preview_line_y, font_default)
                
                # Move help text down by the height of all preview lines plus spacing
                romanji_y = help_y + preview_height_needed + 4

        # Draw main help text
        if romanji_y + line_height <= self.height - 2:
            help_width = self.context["get_text_size"](help_text, font_small)[0]
            help_x = (self.width - help_width) // 2
            self.draw["draw_text"](help_text, help_x, romanji_y, font_small, 255)

    def draw_tts_status_icon(self):
        """Draw TTS status icon in bottom right corner"""
        if self.tts_active and self.tts_state == "speaking":
            # Position in bottom right corner with small margin
            icon_size = 8
            icon_x = self.width - icon_size - 2
            icon_y = self.height - icon_size - 2
            
            # Draw speaker icon
            # Draw speaker base (rectangle)
            self.draw["draw_overlay_area"](icon_x, icon_y + 2, 3, 4, 255)
            # Draw speaker cone (triangle-like)
            self.draw["draw_overlay_area"](icon_x + 3, icon_y + 1, 1, 6, 255)
            self.draw["draw_overlay_area"](icon_x + 4, icon_y, 1, 8, 255)
            # Draw sound waves
            self.draw["draw_overlay_area"](icon_x + 6, icon_y + 2, 1, 1, 255)
            self.draw["draw_overlay_area"](icon_x + 6, icon_y + 5, 1, 1, 255)

    def draw_tts_status_text(self):
        """Draw TTS status text in bottom left corner"""
        if self.tts_active:
            font_small = self.context["fonts"]["small"]
            queue_size = self.tts_queue.qsize()
            
            if queue_size > 0:
                status_text = f"Speaking ({queue_size} queued)"
            else:
                status_text = "Speaking"
            
            # Position in bottom left corner with 2px padding
            status_x = 2
            status_y = self.height - 8  # Leave room for text height
            
            self.draw["draw_overlay_text"](status_text, status_x, status_y, font_small, 255)

    def tts_worker(self):
        """Background worker that processes TTS queue"""
        self.tts_worker_running = True
        print("[Proxi] TTS worker thread started")
        
        try:
            while self.tts_worker_running:
                try:
                    # Wait for next TTS request (with timeout to check if we should stop)
                    text = self.tts_queue.get(timeout=0.5)
                    
                    if text is None:  # Sentinel value to stop worker
                        break
                    
                    # Start TTS playback - show speaking icon immediately
                    self.tts_active = True
                    self.tts_state = "speaking"
                    print(f"[Proxi] Speaking: {text}")
                    
                    try:
                        # Run TTS (generation + playback) - this will handle the thread internally
                        self.context["tts"]["run"](text, background=True)
                        # The tts run function handles threading internally, so we're done when it returns
                        
                        # Mark this task as done
                        self.tts_queue.task_done()
                        print(f"[Proxi] TTS completed for: {text}")
                        
                    except Exception as tts_error:
                        print(f"[Proxi] TTS failed for: {text}, error: {tts_error}")
                        
                        # Reset TTS state immediately to hide speaking icon
                        self.tts_active = False
                        self.tts_state = "idle"
                        
                        # Restore the text to allow retry
                        self.currentline = text
                        self._in_input_mode = True
                        
                        # Update display to show the restored text
                        self.current_suggestion = self.get_autocomplete_suggestion(self.currentline)
                        
                        # Force a UI update to show the restored text immediately
                        self.update_input_display()
                        
                        # Mark this task as done even though it failed
                        try:
                            self.tts_queue.task_done()
                        except ValueError:
                            pass  # task_done called more times than there were items
                    
                    # If no more items in queue, hide icon
                    if self.tts_queue.empty():
                        self.tts_active = False
                        self.tts_state = "idle"
                    
                except queue.Empty:
                    # No new requests, continue checking
                    continue
                except Exception as e:
                    print(f"[Proxi] TTS worker error: {e}")
                    try:
                        self.tts_queue.task_done()
                    except ValueError:
                        pass  # task_done called more times than there were items
                    # Reset state on error
                    if self.tts_queue.empty():
                        self.tts_active = False
                        self.tts_state = "idle"
        finally:
            # TTS worker stopping, hide icon
            self.tts_active = False
            self.tts_state = "idle"
            self.tts_worker_running = False
            print("[Proxi] TTS worker thread stopped")

    def start_tts_worker(self):
        """Start the TTS worker thread if not already running"""
        if not self.tts_worker_running and (not self.tts_thread or not self.tts_thread.is_alive()):
            self.tts_thread = threading.Thread(target=self.tts_worker, daemon=True)
            self.tts_thread.start()

    def add_tts_request(self, text):
        """Add a TTS request to the queue"""
        if text.strip():
            self.tts_queue.put(text.strip())
            self.start_tts_worker()
            print(f"[Proxi] TTS request queued: {text} (Queue size: {self.tts_queue.qsize()})")

    def get_autocomplete_suggestion(self, current_text):
        if not current_text or current_text.endswith(' '):
            return ""
        last_word = current_text.split(' ')[-1].lower()
        if not last_word:  # Extra safety check
            return ""
        
        # Choose the appropriate word list based on Japanese detection
        if self.is_japanese_detected:
            word_list = self.japanese_autocomplete_words
        else:
            word_list = self.autocomplete_words
        
        i = bisect.bisect_left(word_list, last_word)
        while i < len(word_list) and word_list[i].startswith(last_word):
            candidate = word_list[i]
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
            
            # Draw TTS status icon if active
            self.draw_tts_status_icon()
            
            # Draw TTS status text if active
            self.draw_tts_status_text()
                    
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

    def update_romanji_preview(self):
        """Update the Japanese romanji preview if applicable"""
        if self.currentline:
            converted_text, is_japanese = detect_and_convert_romanji(self.currentline)
            if is_japanese and converted_text:
                self.romanji_preview = converted_text
                self.is_japanese_detected = True
            else:
                self.romanji_preview = None
                self.is_japanese_detected = False
        else:
            self.romanji_preview = None
            self.is_japanese_detected = False

    def update_input_display(self):
        """Update the input display with current text and suggestion"""
        self.current_suggestion = self.get_autocomplete_suggestion(self.currentline)
        self.update_romanji_preview()  # Update Japanese preview
        self.draw_interface("Input", "")

    def clear_transient_ui(self):
        """Clear overlay-driven UI state that should not survive app exit."""
        self.tts_active = False
        self.tts_state = "idle"
        self.cursor_visible = False
        self.draw["begin_batch"]()
        try:
            self.draw["clear_overlay_area"](0, 0, self.width, self.height)
        finally:
            self.draw["end_batch"]()

    def start(self):
        print("[Proxi] Started")
        # Initialize cursor state
        self.current_suggestion = ""
        self.cursor_visible = True
        self.cursor_blink_timer = time.time()
        
        # Initialize romanji preview state
        self.romanji_preview = None
        self.is_japanese_detected = False
        
        self.draw_interface("Ready", "Start typing to see suggestions. Press [ESC] to return to launcher.")

    def update(self):
        """Handle cursor blinking and TTS status updates"""
        current_time = time.time()
        cursor_blink_changed = False
        tts_status_changed = False
        
        # Handle cursor blinking only when in input mode
        if current_time - self.cursor_blink_timer > self.cursor_blink_interval:
            self.cursor_visible = not self.cursor_visible
            self.cursor_blink_timer = current_time
            
            # Only mark cursor blink change if we're in input mode
            if self._in_input_mode or self.currentline:
                cursor_blink_changed = True
        
        # Store previous TTS state to detect changes
        if not hasattr(self, 'prev_tts_active'):
            self.prev_tts_active = False
            self.prev_tts_state = "idle"
        
        # Check if TTS state changed
        if (self.tts_active != self.prev_tts_active or 
            self.tts_state != self.prev_tts_state):
            tts_status_changed = True
            self.prev_tts_active = self.tts_active
            self.prev_tts_state = self.tts_state
        
        # Handle different types of updates
        if cursor_blink_changed and not tts_status_changed:
            # Only cursor changed - just update overlay layer
            self.redraw_cursor_only()
        elif tts_status_changed:
            # TTS status changed - need full redraw for status indicators
            if self._in_input_mode or self.currentline:
                self.draw_interface("Input", "")
            else:
                self.draw_interface("Ready", "Start typing to see suggestions. Press [ESC] to return to launcher.")

    
    def onkeydown(self, keycode):
        if keycode == 'KEY_ESC':
            self.clear_transient_ui()
            self.draw_interface("Launcher", "Switching to Launcher...")
            self.context["app_manager"].swap_app_async("proxi", "launcher", update_rate_hz=20.0, delay=0.1)
            return
        
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
            if self.currentline.strip():  # Only process if there's actual text
                # Add TTS request to queue
                self.add_tts_request(self.currentline)
                
                # Clear input immediately and allow new input
                old_line = self.currentline
                self.currentline = ""
                self.current_suggestion = ""
                self._in_input_mode = False  # Reset input mode
                
                # Show ready state
                self.draw_interface("Ready", "Start typing to see suggestions. Press [ESC] to return to launcher.")
                
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
        # Clean up any running TTS
        self.tts_worker_running = False
        
        # Clear the queue and add sentinel value to stop worker
        try:
            while not self.tts_queue.empty():
                self.tts_queue.get_nowait()
                self.tts_queue.task_done()
        except queue.Empty:
            pass
        
        # Add sentinel value to wake up and stop the worker
        self.tts_queue.put(None)
        
        # Wait for worker thread to complete
        if self.tts_thread and self.tts_thread.is_alive():
            print("[Proxi] Waiting for TTS worker thread to complete...")
            self.tts_thread.join(timeout=2.0)  # Wait up to 2 seconds

        self.clear_transient_ui()
