from interfaces import AppBase
from utils.key_repeat import KeyRepeat
from config.keymap import key_map
import os
import time

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.width = context["screen_width"]
        self.height = context["screen_height"]
        self.path = context["app_path"]
        
        # Editor state
        self.lines = [""]  # Content lines
        self.cursor_line = 0  # Current line (0-indexed)
        self.cursor_col = 0   # Current column (0-indexed)
        self.scroll_offset = 0  # Vertical scroll offset
        self.horizontal_scroll = 0  # Horizontal scroll offset
        self.mode = "normal"  # "normal", "insert", "save", "open", "find", "browse", "goto"
        
        # File handling
        self.filename = ""
        self.file_modified = False
        # Set current directory to where the program is running from
        self.current_directory = os.getcwd()  # Get current working directory
        
        # Input buffers for different modes
        self.save_buffer = ""
        self.open_buffer = ""
        self.find_buffer = ""
        self.goto_buffer = ""
        
        # File browser state
        self.browser_directory = self.current_directory
        self.browser_items = []
        self.browser_selection = 0
        self.browser_scroll = 0
        self.browser_visible_items = 9
        
        # Find functionality
        self.find_results = []
        self.current_find_index = 0
        
        # Display settings
        self.visible_lines = 8  # Number of lines visible on screen
        self.visible_lines_insert = 10  # Number of lines visible on screen
        self.status_height = 3  # Lines reserved for status bar
        
        # Hold-to-repeat for navigation and backspace
        self._key_repeat = KeyRepeat()
        self._repeatable_keys = {
            "KEY_BACKSPACE",
            "KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT",
            "KEY_W", "KEY_A", "KEY_S", "KEY_D",
            "KEY_PGUP", "KEY_PGDOWN",
        }

        # Cursor blinking
        self.cursor_blink_timer = 0
        self.cursor_visible = True
        self.cursor_blink_rate = 10  # Blink every 30 ticks (1.5 seconds at 20Hz)
        self.last_cursor_pos = (0, 0)  # Track position changes
        self.last_cursor_draw_pos = None  # Track last drawn cursor position (x, y, width, height)
        
        # Performance optimization
        self.needs_redraw = True
        
    def start(self):
        """Initialize the editor"""
        self.refresh_display()
        
    def mark_for_redraw(self):
        """Mark the editor for redraw on next update cycle"""
        self.needs_redraw = True
        
    def update(self):
        """Update the editor display"""
        if hasattr(self, 't'):
            self.t += 1
        else:
            self.t = 0

        for keycode in self._key_repeat.tick():
            self._dispatch_key(keycode)

        # Handle cursor blinking only in insert mode
        if self.mode == "insert":
            current_pos = (self.cursor_line, self.cursor_col)
            if current_pos != self.last_cursor_pos:
                # Cursor position changed, reset blink cycle
                self.last_cursor_pos = current_pos
                self.cursor_blink_timer = 0
                self.cursor_visible = True
                self.needs_redraw = True
            else:
                # Update blink timer
                self.cursor_blink_timer += 1
                if self.cursor_blink_timer >= self.cursor_blink_rate:
                    self.cursor_visible = not self.cursor_visible
                    self.cursor_blink_timer = 0
                    # Only redraw cursor area, not entire screen
                    self.redraw_cursor_only()
                    return  # Early return to avoid full redraw
        
        # Only redraw when necessary and not too frequently
        if self.needs_redraw:
            self.refresh_display()
            self.needs_redraw = False
    
    def refresh_display(self):
        """Refresh the entire display"""
        # Use batching for improved performance
        self.context["drawing"]["begin_batch"]()
        
        # Clear the screen
        self.context["drawing"]["clear_screen"]()
        
        # Draw the main editor area
        self.draw_editor_content()
        
        # Draw status bar
        self.draw_status_bar()
        
        # Draw cursor
        self.draw_cursor()
        
        # End batch to execute all operations at once
        self.context["drawing"]["end_batch"]()
    
    def redraw_cursor_only(self):
        """Redraw only the cursor without full screen refresh"""
        # Use batching for cursor-only updates
        self.context["drawing"]["begin_batch"]()
        
        # Clear the previous cursor position if it exists
        if self.last_cursor_draw_pos:
            x, y, w, h = self.last_cursor_draw_pos
            self.context["drawing"]["clear_overlay_area"](x, y, w, h)
            self.last_cursor_draw_pos = None
        
        # Draw cursor if visible and in insert mode
        if self.mode == "insert" and self.cursor_visible:
            font = self.context["fonts"]["small"]
            line_height = 5
            
            # Calculate cursor position
            visible_line = self.cursor_line - self.scroll_offset
            if 0 <= visible_line < self.visible_lines:
                y_pos = visible_line * line_height + 1
                
                # Calculate x position based on cursor column with horizontal scrolling
                visible_col = self.cursor_col - self.horizontal_scroll
                if visible_col >= 0:  # Only draw cursor if it's in the visible area
                    # Get the visible portion of the line up to cursor
                    line_text = self.lines[self.cursor_line]
                    start_col = max(0, self.horizontal_scroll)
                    end_col = min(len(line_text), self.cursor_col)
                    
                    if start_col <= end_col:
                        visible_text = line_text[start_col:end_col]
                        text_width, _ = self.context["get_text_size"](visible_text, font)
                        x_pos = 20 + text_width
                        
                        # Draw cursor as a white vertical line
                        self.context["drawing"]["draw_overlay_area"](x_pos, y_pos, 1, line_height, fill=255)
                        
                        # Remember this position for next time
                        self.last_cursor_draw_pos = (x_pos, y_pos, 1, line_height)
        
        self.context["drawing"]["end_batch"]()
    
    def draw_editor_content(self):
        """Draw the main text content"""
        font = self.context["fonts"]["small"]
        line_height = 5  # Adjust based on font size
        visible_lines = self.visible_lines if self.mode == "normal" else self.visible_lines_insert
        
        # Calculate available width for text content (screen width - line number area)
        line_num_width = 20
        content_width = self.width - line_num_width
        
        # Calculate which lines to show
        start_line = self.scroll_offset
        end_line = min(len(self.lines), start_line + visible_lines)

        for i in range(start_line, end_line):
            y_pos = (i - start_line) * line_height + 1
            line_text = self.lines[i] if i < len(self.lines) else ""
            
            highlighted = i == self.cursor_line and self.mode != "insert"
            
            # Highlight current line
            if highlighted:
                self.context["drawing"]["draw_area"](0, y_pos, self.width, line_height, fill=255)  # White background

            # Draw line number
            line_num = f"{i+1:2d}"
            self.context["drawing"]["draw_text"](line_num, 2, y_pos, font, fill=0 if highlighted else 255)
            
            # Apply horizontal scrolling to line content
            if self.horizontal_scroll > 0 and len(line_text) > self.horizontal_scroll:
                visible_text = line_text[self.horizontal_scroll:]
            else:
                visible_text = line_text
            
            # Truncate text that's too long for the visible area
            if visible_text:
                # Calculate how many characters fit in the content width
                char_width = 3  # Approximate character width for the small font
                max_chars = content_width // char_width
                if len(visible_text) > max_chars:
                    visible_text = visible_text[:max_chars]
            
            # Draw line content
            self.context["drawing"]["draw_text"](visible_text, line_num_width, y_pos, font, fill=0 if highlighted else 255)

    def draw_cursor(self):
        """Draw the cursor"""
        # Clear the previous cursor position if it exists
        if self.last_cursor_draw_pos:
            x, y, w, h = self.last_cursor_draw_pos
            self.context["drawing"]["clear_overlay_area"](x, y, w, h)
            self.last_cursor_draw_pos = None
        
        if self.mode == "insert" and self.cursor_visible:
            font = self.context["fonts"]["small"]
            line_height = 5
            
            # Calculate cursor position
            visible_line = self.cursor_line - self.scroll_offset
            if 0 <= visible_line < self.visible_lines:
                y_pos = visible_line * line_height + 1
                
                # Calculate x position based on cursor column with horizontal scrolling
                visible_col = self.cursor_col - self.horizontal_scroll
                if visible_col >= 0:  # Only draw cursor if it's in the visible area
                    # Get the visible portion of the line up to cursor
                    line_text = self.lines[self.cursor_line]
                    start_col = max(0, self.horizontal_scroll)
                    end_col = min(len(line_text), self.cursor_col)
                    
                    if start_col <= end_col:
                        visible_text = line_text[start_col:end_col]
                        text_width, _ = self.context["get_text_size"](visible_text, font)
                        x_pos = 20 + text_width
                        
                        # Draw cursor as a white vertical line
                        self.context["drawing"]["draw_overlay_area"](x_pos, y_pos, 1, line_height, fill=255)
                        
                        # Remember this position for next time
                        self.last_cursor_draw_pos = (x_pos, y_pos, 1, line_height)
    
    def draw_status_bar(self):
        """Draw the status bar at the bottom"""
        font = self.context["fonts"]["small"]
        line_height = 5  # Same as editor content
        status_y = self.height - self.status_height * line_height - 2 # Reserve space for status bar
        
        if self.mode == "normal":
            # Draw the status bar background
            self.context["drawing"]["draw_area"](0, status_y - 1, self.width, line_height * 3 + 2, fill=255)
            
            # Show file info and commands
            file_status = f"F: {self.filename or 'untitled'}"
            if self.file_modified:
                file_status += "*"
            self.context["drawing"]["draw_text"](file_status, 2, status_y, font, fill=0)
            
            cursor_info = f"Ln {self.cursor_line + 1}, Col {self.cursor_col + 1}"
            self.context["drawing"]["draw_text"](cursor_info, 2, status_y + line_height, font, fill=0)
            
            commands = "I:Ins O:Open A+S:Save F:Find G:Goto Q:Quit"
            self.context["drawing"]["draw_text"](commands, 2, status_y + line_height * 2, font, fill=0)
            
        elif self.mode == "insert":
            # Draw the status bar background
            self.context["drawing"]["draw_area"](0, status_y - 1 + line_height * 2, self.width, line_height + 2, fill=255)

            cursor_info = f"{self.cursor_line + 1} / {self.cursor_col + 1} (ins: esc to exit)"
            self.context["drawing"]["draw_text"](cursor_info, 2, status_y + line_height * 2, font, fill=0)
            
        elif self.mode == "save":
            prompt = f"Save as: {self.save_buffer}"
            self.context["drawing"]["draw_text"](prompt, 2, status_y, font, fill=255)
            self.context["drawing"]["draw_text"]("Enter to confirm, Esc to cancel", 2, status_y + line_height, font, fill=255)
            
        elif self.mode == "open":
            prompt = f"Open file: {self.open_buffer}"
            self.context["drawing"]["draw_text"](prompt, 2, status_y, font, fill=255)
            self.context["drawing"]["draw_text"]("Enter to confirm, Esc to cancel", 2, status_y + line_height, font, fill=255)
            
        elif self.mode == "find":
            # Draw the status bar background
            bg_height = line_height * 2 + 2 if self.find_results else line_height + 2
            self.context["drawing"]["draw_area"](0, status_y - 1, self.width, bg_height, fill=255)
            
            prompt = f"Find: {self.find_buffer}"
            self.context["drawing"]["draw_text"](prompt, 2, status_y, font, fill=0)
            if self.find_results:
                result_info = f"Match {self.current_find_index + 1} of {len(self.find_results)}"
                self.context["drawing"]["draw_text"](result_info, 2, status_y + line_height, font, fill=0)
            else:
                help_text = "Enter to search, Esc to cancel"
                self.context["drawing"]["draw_text"](help_text, 2, status_y + line_height, font, fill=0)
        
        elif self.mode == "goto":
            # Draw the status bar background
            self.context["drawing"]["draw_area"](0, status_y - 1 + line_height, self.width, line_height * 2 + 2, fill=255)

            prompt = f"Goto line: {self.goto_buffer}"
            self.context["drawing"]["draw_text"](prompt, 2, status_y + line_height, font, fill=0)
            self.context["drawing"]["draw_text"]("Enter to jump, Esc to cancel", 2, status_y + line_height * 2, font, fill=0)

        elif self.mode == "browse":
            self.draw_file_browser(font, status_y + line_height)
    
    def draw_file_browser(self, font, status_y):
        """Draw the file browser interface"""
        line_height = 5  # Same as other functions
        
        # Draw the status bar background
        self.context["drawing"]["draw_area"](0, status_y - 1, self.width, line_height * 2 + 2, fill=255)
        
        # Show current directory
        dir_display = self.browser_directory
        if len(dir_display) > 20:
            dir_display = "..." + dir_display[-17:]
        self.context["drawing"]["draw_text"](f"|{dir_display}", 2, status_y, font, fill=0)
        
        # Show navigation help
        self.context["drawing"]["draw_text"]("Enter: Select | Esc: Cancel", 2, status_y + line_height, font, fill=0)
        
        # Show file list in the main area
        self.context["drawing"]["draw_area"](0, 0, self.width, status_y - 2, fill=0)  # Clear main area

        if not self.browser_items:
            self.context["drawing"]["draw_text"]("No items in directory", 2, 10, font, fill=255)
            return
        
        # Calculate visible range
        start_item = self.browser_scroll
        end_item = min(len(self.browser_items), start_item + self.browser_visible_items)
        
        for i in range(start_item, end_item):
            y_pos = (i - start_item) * line_height + 1
            item = self.browser_items[i]
            
            # Show item with icon
            if item['is_dir']:
                display_text = f"> {item['name']}"
            else:
                # Check if it's a video file
                _, ext = os.path.splitext(item['name'])
                video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
                if ext.lower() in video_extensions:
                    display_text = f"* {item['name']}"  # * for video files
                else:
                    display_text = f"{item['name']}"
            
            # Truncate long names
            if len(display_text) > 30:
                display_text = display_text[:27] + "..."
            # Draw selected item with inverted text
            if i == self.browser_selection:
                self.draw_inverted_text(font, display_text, 2, y_pos)
            else:
                self.context["drawing"]["draw_text"](display_text, 2, y_pos, font, fill=255)
        
        # Show scroll indicator if needed (overlay on the status bar background)
        if len(self.browser_items) > self.browser_visible_items:
            scroll_info = f"{self.browser_selection + 1}/{len(self.browser_items)}"
            # Calculate position to right-align the scroll info
            scroll_width, _ = self.context["get_text_size"](scroll_info, font)
            scroll_x = self.width - scroll_width - 2
            self.context["drawing"]["draw_text"](scroll_info, scroll_x, status_y + line_height, font, fill=0)
    
    def draw_inverted_text(self, font, text, x, y):
        """Draw text with inverted colors (white background, black text)"""
        from PIL import Image, ImageDraw
        
        # Get text dimensions
        text_width, text_height = self.context["get_text_size"](text, font)
        
        # Create inverted background
        bg_width = text_width + 1  # Small padding
        bg_height = text_height + 2
        
        # Create white background image
        bg_img = Image.new("1", (bg_width, bg_height), 1)  # White background
        draw = ImageDraw.Draw(bg_img)
        
        # Draw black text on white background
        draw.text((1, 0), text, font=font, fill=0)  # Black text with 1px padding
        
        # Draw the inverted text image using context drawing
        self.context["drawing"]["draw_image"](bg_img, x-1, y)
    
    def onkeydown(self, keycode):
        """Handle key presses."""
        if keycode in self._repeatable_keys:
            self._key_repeat.press(keycode)
        self._dispatch_key(keycode)

    def onkeyup(self, keycode):
        """Handle key releases."""
        self._key_repeat.release(keycode)

    def _dispatch_key(self, keycode):
        if self.mode == "normal":
            self.handle_normal_mode(keycode)
        elif self.mode == "insert":
            self.handle_insert_mode(keycode)
        elif self.mode == "save":
            self.handle_save_mode(keycode)
        elif self.mode == "open":
            self.handle_open_mode(keycode)
        elif self.mode == "find":
            self.handle_find_mode(keycode)
        elif self.mode == "goto":
            self.handle_goto_mode(keycode)
        elif self.mode == "browse":
            self.handle_browse_mode(keycode)
    
    def handle_normal_mode(self, keycode):
        """Handle keys in normal mode"""
        if keycode == "KEY_I":
            self.mode = "insert"
            self.cursor_blink_timer = 0
            self.cursor_visible = True
            self.mark_for_redraw()
            
        elif keycode == "KEY_O":
            self.mode = "browse"
            self.init_file_browser()
            self.mark_for_redraw()  # Mode change requires redraw
            
        elif keycode == "KEY_CTRL_O":  # Ctrl+O for quick filename entry
            self.mode = "open"
            self.open_buffer = ""
            self.mark_for_redraw()  # Mode change requires redraw
            
        # Alt+S for quick save
        elif keycode == "KEY_S" and "KEY_RIGHTALT" in self.context["pressed_keys"]:
            self.mode = "save"
            self.save_buffer = self.filename
            self.mark_for_redraw()  # Mode change requires redraw
            
        elif keycode == "KEY_F":
            self.mode = "find"
            self.find_buffer = ""
            self.mark_for_redraw()  # Mode change requires redraw
            
        elif keycode == "KEY_G":
            self.mode = "goto"
            self.goto_buffer = ""
            self.mark_for_redraw()  # Mode change requires redraw
            
            
        elif keycode == "KEY_Q":
            if self.file_modified:
                print("[Code Editor] File has unsaved changes. Save first with ALT+S.")
            else:
                # Use context drawing to show transition message
                self.context["app_manager"].swap_app_async("code_editor", "launcher", update_rate_hz=20.0, delay=0.1)
        
        # Navigation - these require redraws
        elif keycode == "KEY_UP" or keycode == "KEY_W":
            self.move_cursor(-1, 0)
            self.mark_for_redraw()
        elif keycode == "KEY_DOWN"or keycode == "KEY_S":
            self.move_cursor(1, 0)
            self.mark_for_redraw()
        elif keycode == "KEY_LEFT" or keycode == "KEY_A":
            self.move_cursor(0, -1)
            self.mark_for_redraw()
        elif keycode == "KEY_RIGHT" or keycode == "KEY_D":
            self.move_cursor(0, 1)
            self.mark_for_redraw()
        elif keycode == "KEY_HOME":
            self.cursor_col = 0
            self.mark_for_redraw()
        elif keycode == "KEY_END":
            self.cursor_col = len(self.lines[self.cursor_line])
            self.mark_for_redraw()
        elif keycode == "KEY_PGUP":
            self.move_cursor(-self.visible_lines, 0)
            self.mark_for_redraw()
        elif keycode == "KEY_PGDOWN":
            self.move_cursor(self.visible_lines, 0)
            self.mark_for_redraw()
            
        elif keycode == "KEY_ESC":
            self.context["app_manager"].swap_app_async("code_editor", "launcher", update_rate_hz=20.0, delay=0.1)
    
    def handle_insert_mode(self, keycode):
        """Handle keys in insert mode"""
        if keycode == "KEY_ESC":
            self.mode = "normal"
            self.cursor_visible = False
            self._key_repeat.release_all()
            self.mark_for_redraw()
            return
            
        # Handle special keys - these modify content so need redraw
        if keycode == "KEY_ENTER":
            self.insert_newline()
            self.mark_for_redraw()
        elif keycode == "KEY_BACKSPACE":
            self.delete_char()
            self.mark_for_redraw()
        elif keycode == "KEY_TAB":
            self.insert_text("    ")  # 4 spaces for tab
            self.mark_for_redraw()
        elif keycode == "KEY_UP":
            self.move_cursor(-1, 0)
            # Don't redraw for cursor movement in insert mode - cursor blink handles it
        elif keycode == "KEY_DOWN":
            self.move_cursor(1, 0)
            # Don't redraw for cursor movement in insert mode - cursor blink handles it
        elif keycode == "KEY_LEFT":
            self.move_cursor(0, -1)
            # Don't redraw for cursor movement in insert mode - cursor blink handles it
        elif keycode == "KEY_RIGHT":
            self.move_cursor(0, 1)
            # Don't redraw for cursor movement in insert mode - cursor blink handles it
        else:
            # Handle character input - this modifies content so needs redraw
            char = key_map.get(keycode, "")
            if char:
                self.insert_text(char)
                self.mark_for_redraw()
    
    def handle_save_mode(self, keycode):
        """Handle keys in save mode"""
        if keycode == "KEY_ESC":
            self.mode = "normal"
            self.mark_for_redraw()  # Mode change requires redraw
            return
            
        if keycode == "KEY_ENTER":
            if self.save_buffer:
                self.save_file(self.save_buffer)
            self.mode = "normal"
            self.mark_for_redraw()  # Mode change requires redraw
            return
            
        if keycode == "KEY_BACKSPACE":
            if self.save_buffer:
                self.save_buffer = self.save_buffer[:-1]
                self.mark_for_redraw()  # Buffer change requires redraw
            return
            
        char = key_map.get(keycode, "")
        if char and char.isprintable():
            self.save_buffer += char
            self.mark_for_redraw()  # Buffer change requires redraw
    
    def handle_open_mode(self, keycode):
        """Handle keys in open mode"""
        if keycode == "KEY_ESC":
            self.mode = "normal"
            self.mark_for_redraw()  # Mode change requires redraw
            return
            
        if keycode == "KEY_ENTER":
            if self.open_buffer:
                self.open_file(self.open_buffer)
            self.mode = "normal"
            self.mark_for_redraw()  # Mode change requires redraw
            return
            
        if keycode == "KEY_BACKSPACE":
            if self.open_buffer:
                self.open_buffer = self.open_buffer[:-1]
                self.mark_for_redraw()  # Buffer change requires redraw
            return
            
        char = key_map.get(keycode, "")
        if char and char.isprintable():
            self.open_buffer += char
            self.mark_for_redraw()  # Buffer change requires redraw
    
    def handle_find_mode(self, keycode):
        """Handle keys in find mode"""
        if keycode == "KEY_ESC":
            self.mode = "normal"
            self.find_results = []
            self.mark_for_redraw()  # Mode change requires redraw
            return
            
        if keycode == "KEY_ENTER":
            if self.find_buffer:
                self.perform_search()
                self.mark_for_redraw()  # Search results require redraw
            else:
                self.mode = "normal"
                self.mark_for_redraw()  # Mode change requires redraw
            return
            
        if keycode == "KEY_BACKSPACE":
            if self.find_buffer:
                self.find_buffer = self.find_buffer[:-1]
                self.mark_for_redraw()  # Buffer change requires redraw
            return
            
        if keycode == "KEY_F3" or keycode == "KEY_DOWN":
            self.next_find_result()
            self.mark_for_redraw()  # Cursor movement requires redraw
            return
            
        char = key_map.get(keycode, "")
        if char and char.isprintable():
            self.find_buffer += char
            self.mark_for_redraw()  # Buffer change requires redraw
    
    def handle_goto_mode(self, keycode):
        """Handle keys in goto mode"""
        if keycode == "KEY_ESC":
            self.mode = "normal"
            self.mark_for_redraw()  # Mode change requires redraw
            return
            
        if keycode == "KEY_ENTER":
            if self.goto_buffer:
                self.goto_line()
                self.mark_for_redraw()  # Cursor movement requires redraw
            else:
                self.mode = "normal"
                self.mark_for_redraw()  # Mode change requires redraw
            return
            
        if keycode == "KEY_BACKSPACE":
            if self.goto_buffer:
                self.goto_buffer = self.goto_buffer[:-1]
                self.mark_for_redraw()  # Buffer change requires redraw
            return
            
        # Only allow digits for line numbers
        char = key_map.get(keycode, "")
        if char and char.isdigit():
            self.goto_buffer += char
            self.mark_for_redraw()  # Buffer change requires redraw
    
    def handle_browse_mode(self, keycode):
        """Handle keys in file browser mode"""
        if keycode == "KEY_ESC":
            self.mode = "normal"
            self.mark_for_redraw()  # Mode change requires redraw
            return
            
        if keycode == "KEY_ENTER":
            if self.browser_items and 0 <= self.browser_selection < len(self.browser_items):
                selected_item = self.browser_items[self.browser_selection]
                if selected_item['is_dir']:
                    # Enter directory
                    if selected_item['name'] == "..":
                        # Go up one directory
                        parent = os.path.dirname(self.browser_directory)
                        if parent != self.browser_directory:  # Prevent going above root
                            self.browser_directory = parent
                    else:
                        # Enter subdirectory
                        self.browser_directory = os.path.join(self.browser_directory, selected_item['name'])
                    self.init_file_browser()
                    self.mark_for_redraw()  # Directory change requires redraw
                else:
                    # Open file
                    filepath = os.path.join(self.browser_directory, selected_item['name'])
                    
                    # Check if it's a video file before changing mode
                    _, ext = os.path.splitext(filepath)
                    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
                    is_video = ext.lower() in video_extensions
                    
                    if is_video:
                        print(f"[Code Editor] Video file selected, delegating to video handler")
                    
                    self.open_file_direct(filepath)
                    
                    # Only change mode back to normal if it's not a video file
                    # (video files will trigger app swap, so we shouldn't change mode)
                    if not is_video:
                        self.mode = "normal"
                        self.mark_for_redraw()  # Mode change requires redraw
            return
            
        if keycode == "KEY_UP" or keycode == "KEY_W":
            if self.browser_selection > 0:
                self.browser_selection -= 1
                # Adjust scroll if needed
                if self.browser_selection < self.browser_scroll:
                    self.browser_scroll = self.browser_selection
                self.mark_for_redraw()  # Selection change requires redraw
            return
            
        if keycode == "KEY_DOWN" or keycode == "KEY_S":
            if self.browser_selection < len(self.browser_items) - 1:
                self.browser_selection += 1
                # Adjust scroll if needed
                if self.browser_selection >= self.browser_scroll + self.browser_visible_items:
                    self.browser_scroll = self.browser_selection - self.browser_visible_items + 1
                self.mark_for_redraw()  # Selection change requires redraw
            return
            
        if keycode == "KEY_HOME":
            self.browser_selection = 0
            self.browser_scroll = 0
            self.mark_for_redraw()  # Selection change requires redraw
            return
            
        if keycode == "KEY_END":
            self.browser_selection = len(self.browser_items) - 1
            self.browser_scroll = max(0, self.browser_selection - self.browser_visible_items + 1)
            self.mark_for_redraw()  # Selection change requires redraw
            return
    
    def init_file_browser(self):
        """Initialize the file browser for current directory"""
        try:
            self.browser_items = []
            
            # Add parent directory option if not at root
            parent = os.path.dirname(self.browser_directory)
            if parent != self.browser_directory:
                self.browser_items.append({
                    'name': '..',
                    'is_dir': True,
                    'path': parent
                })
            
            # Get directory contents
            items = os.listdir(self.browser_directory)
            
            # Separate directories and files
            dirs = []
            files = []
            
            for item in items:
                item_path = os.path.join(self.browser_directory, item)
                if os.path.isdir(item_path):
                    dirs.append({
                        'name': item,
                        'is_dir': True,
                        'path': item_path
                    })
                else:
                    # Show text files, code files, and video files
                    _, ext = os.path.splitext(item)
                    allowed_extensions = ['.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.md', '.cfg', '.ini', '.log', 
                                        '.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '']
                    if ext.lower() in allowed_extensions or not ext:
                        files.append({
                            'name': item,
                            'is_dir': False,
                            'path': item_path
                        })
            
            # Sort directories and files separately
            dirs.sort(key=lambda x: x['name'].lower())
            files.sort(key=lambda x: x['name'].lower())
            
            # Add to browser items (directories first)
            self.browser_items.extend(dirs)
            self.browser_items.extend(files)
            
            # Reset selection
            self.browser_selection = 0
            self.browser_scroll = 0
            
        except Exception as e:
            print(f"[Code Editor] Error accessing directory: {str(e)}")
            self.mode = "normal"
    
    def move_cursor(self, line_delta, col_delta):
        """Move cursor by given deltas"""
        new_line = max(0, min(len(self.lines) - 1, self.cursor_line + line_delta))
        
        if new_line != self.cursor_line:
            self.cursor_line = new_line
            # Adjust column to fit new line
            self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
        
        if col_delta != 0:
            new_col = max(0, min(len(self.lines[self.cursor_line]), self.cursor_col + col_delta))
            self.cursor_col = new_col
        
        # Adjust vertical scroll if cursor is out of view
        if self.cursor_line < self.scroll_offset:
            self.scroll_offset = self.cursor_line
        elif self.cursor_line >= self.scroll_offset + self.visible_lines:
            self.scroll_offset = self.cursor_line - self.visible_lines + 1
        
        # Adjust horizontal scroll if cursor is out of view
        self.adjust_horizontal_scroll()
    
    def adjust_horizontal_scroll(self):
        """Adjust horizontal scroll to keep cursor in view"""
        # Calculate available width for text content
        line_num_width = 20
        content_width = self.width - line_num_width
        
        # Approximate character width
        char_width = 3
        visible_chars = content_width // char_width
        
        # Start scrolling sooner by reducing effective visible area
        scroll_margin = 5  # Start scrolling when 5 characters from edge
        effective_visible_chars = max(10, visible_chars - (scroll_margin * 2))
        
        # Adjust horizontal scroll to keep cursor visible
        if self.cursor_col < self.horizontal_scroll + scroll_margin:
            # Cursor is getting close to the left edge
            self.horizontal_scroll = max(0, self.cursor_col - scroll_margin)
        elif self.cursor_col >= self.horizontal_scroll + effective_visible_chars:
            # Cursor is getting close to the right edge
            self.horizontal_scroll = self.cursor_col - effective_visible_chars + scroll_margin
    
    def insert_text(self, text):
        """Insert text at cursor position"""
        line = self.lines[self.cursor_line]
        new_line = line[:self.cursor_col] + text + line[self.cursor_col:]
        self.lines[self.cursor_line] = new_line
        self.cursor_col += len(text)
        self.file_modified = True
        
        # Adjust horizontal scroll after inserting text
        self.adjust_horizontal_scroll()
    
    def insert_newline(self):
        """Insert a new line at cursor position"""
        line = self.lines[self.cursor_line]
        before = line[:self.cursor_col]
        after = line[self.cursor_col:]
        
        self.lines[self.cursor_line] = before
        self.lines.insert(self.cursor_line + 1, after)
        self.cursor_line += 1
        self.cursor_col = 0
        self.file_modified = True
        
        # Reset horizontal scroll when moving to new line
        self.horizontal_scroll = 0
        
        # Adjust scroll if necessary
        if self.cursor_line >= self.scroll_offset + self.visible_lines:
            self.scroll_offset += 1
    
    def delete_char(self):
        """Delete character before cursor (backspace)"""
        if self.cursor_col > 0:
            # Delete character on current line
            line = self.lines[self.cursor_line]
            new_line = line[:self.cursor_col-1] + line[self.cursor_col:]
            self.lines[self.cursor_line] = new_line
            self.cursor_col -= 1
        elif self.cursor_line > 0:
            # Join with previous line
            prev_line = self.lines[self.cursor_line - 1]
            curr_line = self.lines[self.cursor_line]
            self.lines[self.cursor_line - 1] = prev_line + curr_line
            del self.lines[self.cursor_line]
            self.cursor_line -= 1
            self.cursor_col = len(prev_line)
            
            # Adjust scroll if necessary
            if self.cursor_line < self.scroll_offset:
                self.scroll_offset = max(0, self.scroll_offset - 1)
        
        self.file_modified = True
        
        # Adjust horizontal scroll after deleting
        self.adjust_horizontal_scroll()
    
    def save_file(self, filename):
        """Save the current content to a file"""
        try:
            # Add .txt extension if no extension provided
            if not os.path.splitext(filename)[1]:
                filename += ".txt"
                
            filepath = os.path.join(self.current_directory, filename)
            
            print(f"Saving file to {filepath}")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.lines))
            
            self.filename = filename
            self.file_modified = False
            print(f"[Code Editor] Saved {filename}")

        except Exception as e:
            print(f"[Code Editor] Error saving file: {str(e)}")
    
    def open_file(self, filename):
        """Open a file for editing"""
        try:
            # Add .txt extension if no extension provided
            if not os.path.splitext(filename)[1]:
                filename += ".txt"
                
            filepath = os.path.join(self.current_directory, filename)
            
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self.lines = content.split('\n') if content else [""]
                self.cursor_line = 0
                self.cursor_col = 0
                self.scroll_offset = 0
                self.filename = filename
                self.file_modified = False
                # self.context["tts"]["run"](f"Opened {filename}", background=True)
            else:
                # Create new file
                self.lines = [""]
                self.cursor_line = 0
                self.cursor_col = 0
                self.scroll_offset = 0
                self.filename = filename
                self.file_modified = False
                # self.context["tts"]["run"](f"Creating new file {filename}", background=True)
                
        except Exception as e:
            print(f"Error opening file: {str(e)}")
            # self.context["tts"]["run"](f"Error opening file: {str(e)}", background=True)
    
    def open_file_direct(self, filepath):
        """Open a file directly using its full path"""
        try:
            if os.path.exists(filepath):
                # Check if it's a video file
                video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
                file_ext = os.path.splitext(filepath)[1].lower()
                
                if file_ext in video_extensions:
                    # Launch video player
                    print(f"[Code Editor] Detected video file: {filepath}")
                    print(f"[Code Editor] Available apps: {[app['name'] for app in self.context['apps']['all']]}")
                    
                    # Store the file path for the video player to pick up
                    if not hasattr(self.context, 'pending_video_file'):
                        self.context['pending_video_file'] = filepath
                    else:
                        self.context['pending_video_file'] = filepath
                    
                    print(f"[Code Editor] Stored video file path: {filepath}")
                    
                    # Swap to video player - it will check for pending_video_file
                    self.context["app_manager"].swap_app_async("code_editor", "video_player", update_rate_hz=20.0, delay=0.1)
                    print(f"[Code Editor] App swap requested")
                    return
                
                # Regular text file opening
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self.lines = content.split('\n') if content else [""]
                self.cursor_line = 0
                self.cursor_col = 0
                self.scroll_offset = 0
                self.filename = os.path.basename(filepath)
                self.current_directory = os.path.dirname(filepath)
                self.file_modified = False
                print(f"[Code Editor] Opened {self.filename}")
            else:
                print("[Code Editor] File not found")

        except Exception as e:
            print(f"[Code Editor] Error opening file: {str(e)}")
    
    def perform_search(self):
        """Search for text in the document"""
        self.find_results = []
        search_term = self.find_buffer.lower()
        
        for line_num, line in enumerate(self.lines):
            line_lower = line.lower()
            start = 0
            while True:
                pos = line_lower.find(search_term, start)
                if pos == -1:
                    break
                self.find_results.append((line_num, pos))
                start = pos + 1
        
        if self.find_results:
            self.current_find_index = 0
            self.jump_to_find_result(0)
            # self.context["tts"]["run"](f"Found {len(self.find_results)} matches", background=True)
        else:
            # self.context["tts"]["run"]("No matches found", background=True)
            print("No matches found")

    def next_find_result(self):
        """Jump to next search result"""
        if self.find_results:
            self.current_find_index = (self.current_find_index + 1) % len(self.find_results)
            self.jump_to_find_result(self.current_find_index)
    
    def jump_to_find_result(self, index):
        """Jump cursor to specific search result"""
        if 0 <= index < len(self.find_results):
            line_num, col_num = self.find_results[index]
            self.cursor_line = line_num
            self.cursor_col = col_num
            
            # Adjust scroll to show the result
            if self.cursor_line < self.scroll_offset:
                self.scroll_offset = self.cursor_line
            elif self.cursor_line >= self.scroll_offset + self.visible_lines:
                self.scroll_offset = self.cursor_line - self.visible_lines + 1
            
            # Adjust horizontal scroll to show the found text
            self.adjust_horizontal_scroll()
    
    def goto_line(self):
        """Jump to the specified line number"""
        try:
            target_line = int(self.goto_buffer) - 1  # Convert to 0-based index
            
            # Bounds checking
            if target_line < 0:
                target_line = 0
            elif target_line >= len(self.lines):
                target_line = len(self.lines) - 1
                
            # Move cursor to beginning of target line
            self.cursor_line = target_line
            self.cursor_col = 0
            
            # Adjust vertical scrolling to show the target line
            if self.cursor_line < self.scroll_offset:
                self.scroll_offset = self.cursor_line
            elif self.cursor_line >= self.scroll_offset + self.visible_lines:
                self.scroll_offset = self.cursor_line - self.visible_lines + 1
                
            # Adjust horizontal scrolling
            self.adjust_horizontal_scroll()
            
            # Exit goto mode
            self.mode = "normal"
            self.goto_buffer = ""
            
        except ValueError:
            # Invalid line number, just exit goto mode
            self.mode = "normal"
            self.goto_buffer = ""
    
    def stop(self):
        """Clean up when app stops"""
        pass
