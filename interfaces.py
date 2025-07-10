class AppBase:
    def __init__(self, context):
        """
        context: dict containing shared functions and state (e.g., display, TTS, etc.)
        """
        self.context = context

    def start(self):
        pass

    def update(self):
        pass
    
    def onkeydown(self, keycode):
        pass

    def onkeyup(self, keycode):
        pass
    
    def stop(self):
        pass
        
    def set_screen(self, title, text):
        """
        Render a screen with title and text using the app's own rendering logic.
        This replaces the centralized set_screen display queue command.
        """
        from PIL import Image, ImageDraw
        import math
        
        # Get context variables
        display_queue = self.context["display_queue"]
        width = self.context["screen_width"]
        height = self.context["screen_height"]
        font_small = self.context["fonts"]["small"]
        get_text_size = self.context["get_text_size"]
        
        # Clear the display
        display_queue.put(("clear_base",))
        
        # Always clear cursor for apps that use cursor positioning
        if hasattr(self, '_update_cursor_position'):
            display_queue.put(("clear_cursor_area",))
          # Text wrapping function with highlight support
        def wrap_text_by_pixel_width(text, font, max_width):
            import re
            
            # Parse text for highlights [text] and regular text
            def parse_text_segments(text):
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
            
            segments = parse_text_segments(text)
            lines = []
            current_line_segments = []
            current_line_width = 0
            
            # Process each character-level segment
            for segment_idx, segment in enumerate(segments):
                if not segment['text']:
                    continue
                
                # For each segment, we need to handle word breaking properly
                # Split by spaces but keep track of highlighting
                words = segment['text'].split(' ')
                
                for word_idx, word in enumerate(words):
                    # if not word:  # Skip empty words from consecutive spaces
                    #     continue
                    
                    # Determine if we need a space before this word
                    needs_space = False
                    
                    if word_idx > 0:
                        # Always add space between words within the same segment
                        needs_space = True
                    elif current_line_segments and current_line_segments[-1]['text']:
                        # Check if we need a space when transitioning between segments
                        prev_segment = current_line_segments[-1]
                        
                        # Check if the original text had a space at this position
                        # Look at the raw text to see if there should be a space
                        if segment_idx > 0:
                            prev_segment_in_original = segments[segment_idx - 1]
                            current_segment_in_original = segments[segment_idx]
                            
                            # Check if there was originally a space between these segments
                            # by looking at the end of prev segment and start of current segment
                            prev_ends_with_space = prev_segment_in_original['text'].endswith(' ')
                            current_starts_with_space = current_segment_in_original['text'].startswith(' ')
                            
                            # Add space only if there was originally a space
                            if prev_ends_with_space or current_starts_with_space:
                                needs_space = True
                        else:
                            # First segment after some text, check if we need space
                            # This handles normal word boundaries
                            needs_space = True
                    
                    if needs_space:
                        space_width = get_text_size(' ', font)[0]
                        if current_line_width + space_width <= max_width:
                            current_line_segments.append({
                                'text': ' ',
                                'highlighted': False
                            })
                            current_line_width += space_width
                        else:
                            # Start new line if space doesn't fit
                            if current_line_segments:
                                lines.append(current_line_segments)
                            current_line_segments = []
                            current_line_width = 0
                    
                    # Now handle the word itself
                    word_width = get_text_size(word, font)[0]
                    
                    if current_line_width + word_width <= max_width:
                        # Word fits on current line
                        current_line_segments.append({
                            'text': word,
                            'highlighted': segment['highlighted']
                        })
                        current_line_width += word_width
                    else:
                        # Word doesn't fit, start new line
                        if current_line_segments:
                            lines.append(current_line_segments)
                        current_line_segments = [{
                            'text': word,
                            'highlighted': segment['highlighted']
                        }]
                        current_line_width = word_width
            
            # Add the last line
            if current_line_segments:
                lines.append(current_line_segments)
            
            return lines
        
        def render_highlighted_line(segments, x, y, font):
            """Render a line with highlighted segments"""
            current_x = x
            
            for segment in segments:
                if not segment['text']:
                    continue
                    
                text_width, text_height = get_text_size(segment['text'], font)
                
                if segment['highlighted']:
                    # Create highlighted background without x padding
                    bg_width = text_width + 1  # No padding added
                    bg_height = text_height + 2
                    
                    # Create white background image
                    bg_img = Image.new("1", (bg_width, bg_height), 1)  # White background
                    draw = ImageDraw.Draw(bg_img)
                    
                    # Draw black text on white background without x offset
                    draw.text((1, 0), segment['text'], font=font, fill=0)  # Black text, no x offset
                    
                    # Draw the background with text
                    display_queue.put(("draw_base_image", bg_img, current_x, y))
                    current_x += bg_width
                else:
                    # Regular text (white text on black background)
                    display_queue.put(("draw_base_text", font, segment['text'], current_x, y))
                    current_x += text_width
        
        # Layout constants
        padding = 2
        side_padding = 4  # Add side padding for body text
        bodyLineHeight = 4
        
        # Render title
        title_width, title_height = get_text_size(title, font_small)
        title_x = (width - title_width) // 2
        title_y = padding
        display_queue.put(("draw_base_text", font_small, title, title_x, title_y))
        
        # Render wrapped text with highlight support
        wrapped_lines = wrap_text_by_pixel_width(text, font_small, width - (side_padding * 2))
        start_y = title_y + title_height + padding
        max_lines = (height - start_y) // bodyLineHeight
        
        line_y = start_y
        
        for i in range(min(len(wrapped_lines), max_lines)):
            render_highlighted_line(wrapped_lines[i], side_padding, line_y, font_small)
            
            # Update cursor position for apps that need it (only on the last line with content)
            if hasattr(self, '_update_cursor_position') and i == min(len(wrapped_lines), max_lines) - 1:
                # Clear cursor first to ensure proper positioning
                display_queue.put(("clear_cursor_area",))
                
                # Calculate cursor position at the end of all text (including highlighted text)
                cursor_x = side_padding  # Start cursor position at the side padding
                for j, segment in enumerate(wrapped_lines[i]):
                    segment_width, _ = get_text_size(segment['text'], font_small)
                    if segment['highlighted']:
                        # Check if previous segment was a space (for spacing adjustment)
                        if j > 0 and wrapped_lines[i][j-1]['text'] == ' ' and not wrapped_lines[i][j-1]['highlighted']:
                            # Account for reduced spacing before highlighted text
                            cursor_x -= segment_width  # Remove normal space width
                            cursor_x += 2  # Add only 2 pixels of space
                        cursor_x += segment_width + 1  # Add the background width
                    else:
                        cursor_x += segment_width
                display_queue.put(("set_cursor_position", cursor_x, line_y))
                
            line_y += bodyLineHeight + padding

    def set_screen_with_cursor(self, title, text):
        """
        Set screen and enable cursor positioning for text input apps.
        """
        self._update_cursor_position = True
        self.set_screen(title, text)
        
    def show_message(self, title, message, duration=2):
        """
        Show a temporary message screen.
        """
        import time
        self.set_screen(title, message)
        time.sleep(duration)
        
    def show_error(self, error_message):
        """
        Show an error screen.
        """
        self.set_screen("Error", error_message)
        
    def show_loading(self, message="Loading..."):
        """
        Show a loading screen.
        """
        self.set_screen("Loading", message)
