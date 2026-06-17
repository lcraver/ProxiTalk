import re
import requests
import html
import os
import hashlib
import time
import threading
import io
from PIL import Image
from interfaces import AppBase
from config.keymap import key_map
from utils.image_utils import AppImageUtils

# Basic HTML element representation
class HTMLElement:
    def __init__(self, tag, attrs, text, is_interactive):
        self.tag = tag
        self.attrs = attrs
        self.text = text
        self.is_interactive = is_interactive
        self.rect = None  # Will be set during rendering

# Simple HTML parser for links and inputs
class SimpleHTMLRenderer:
    def __init__(self, html_text):
        self.input_buffers = {}  # key: input element id (id(self)), value: str
        self.selected_index = 0
        self.last_selected_input = None
        self.scroll_offset = 0  # For scrolling through content
        self.cached_display_lines = None  # Cache wrapped lines for performance
        self.last_screen_width = None
        self.last_selected_index = None
        self.last_input_buffers_hash = None  # Track input buffer changes
        self.image_cache = {}  # Cache downloaded and processed images
        self.base_url = 'http://frogfind.com'  # Default base URL for relative image URLs
        self.elements = self.parse(html_text)

    def parse(self, html_text):
        elements = []
        self.forms = []
        
        # First pass: Find forms and their spans
        form_iter = re.finditer(r'<form([^>]*)>(.*?)</form>', html_text, re.I|re.S)
        form_spans = []
        for m in form_iter:
            form_spans.append((m.start(), m.end(), m.group(1), m.group(2)))
        
        # Mark which character positions belong to which form
        element_forms = {}
        for idx, (start, end, form_attrs, form_content) in enumerate(form_spans):
            for i in range(start, end):
                element_forms[i] = idx
            # Parse form attributes
            attrs = dict(re.findall(r'(\w+)=[\"\\\']([^\"\\\']+)[\"\\\']', form_attrs))
            self.forms.append({'attrs': attrs, 'inputs': []})
        
        # Second pass: Find all elements in document order
        # Create a list of all matches with their positions
        all_matches = []
        
        # Find links
        for match in re.finditer(r'<a [^>]*href=["\\\']([^"\\\']+)["\\\'][^>]*>(.*?)</a>', html_text, re.I|re.S):
            href, text = match.groups()
            # Strip font tags and color attributes from link text
            clean_text = re.sub(r'<font[^>]*>', '', text)
            clean_text = re.sub(r'</font>', '', clean_text)
            clean_text = re.sub(r'<[^>]+>', '', clean_text)  # Remove any other HTML tags
            all_matches.append((match.start(), 'a', {'href': href}, html.unescape(clean_text), True))
        
        # Find inputs
        for match in re.finditer(r'<input [^>]*>', html_text, re.I):
            attrs = dict(re.findall(r'(\w+)=["\\\']([^"\\\']+)["\\\']', match.group(0)))
            input_type = attrs.get('type', '').lower()
            if input_type == 'submit':
                all_matches.append((match.start(), 'submit', attrs, attrs.get('value', 'Submit'), True))
            else:
                # For all other input types, initialize value from HTML
                initial_value = attrs.get('value', '')
                all_matches.append((match.start(), 'input', attrs, initial_value, True))
        
        # Find paragraphs and headers
        for match in re.finditer(r'<(p|h[1-6])[^>]*>(.*?)</\\1>', html_text, re.I|re.S):
            tag, text = match.groups()
            # Strip font tags and color attributes
            clean_text = re.sub(r'<font[^>]*>', '', text)
            clean_text = re.sub(r'</font>', '', clean_text)
            clean_text = re.sub(r'<[^>]+>', '', clean_text)  # Remove any other HTML tags
            all_matches.append((match.start(), tag, {}, html.unescape(clean_text), False))
        
        # Find line breaks
        for match in re.finditer(r'<br\s*/?>', html_text, re.I):
            all_matches.append((match.start(), 'br', {}, '', False))
        
        # Find images
        for match in re.finditer(r'<img [^>]*>', html_text, re.I):
            attrs = dict(re.findall(r'(\w+)=["\\\']([^"\\\']+)["\\\']', match.group(0)))
            img_src = attrs.get('src', '')
            img_alt = attrs.get('alt', 'Image')
            if img_src:
                print(f"[FrogFind] Found image tag #{len([m for m in all_matches if m[1] == 'img']) + 1}: src={img_src}, alt={img_alt}")
                all_matches.append((match.start(), 'img', {'src': img_src, 'alt': img_alt}, img_alt, False))
        
        # Find substantial text segments between tags
        # Split by HTML tags and process text segments
        tag_positions = [(match.start(), match.end()) for match in re.finditer(r'<[^>]+>', html_text)]
        text_pos = 0
        for tag_start, tag_end in tag_positions + [(len(html_text), len(html_text))]:
            # Get text before this tag
            text_segment = html_text[text_pos:tag_start].strip()
            if len(text_segment) > 15 and not text_segment.isspace():
                clean_text = html.unescape(text_segment)
                # Only add if it's not already covered by other elements
                all_matches.append((text_pos, 'text', {}, clean_text, False))
            text_pos = tag_end
        
        # Sort all matches by document position
        all_matches.sort(key=lambda x: x[0])
        
        # Create HTMLElement objects in document order
        for pos, tag, attrs, text, is_interactive in all_matches:
            el = HTMLElement(tag, attrs, text, is_interactive)
            
            # Initialize input buffer for input elements
            if tag == 'input':
                self.input_buffers[id(el)] = text
            
            # Start image download for img elements
            if tag == 'img':
                # Use callback if available
                callback = getattr(self, 'image_load_callback', None)
                self.start_image_download(el, callback)
            
            # Assign to form if inside one
            form_idx = None
            if pos in element_forms:
                form_idx = element_forms[pos]
                el.form_idx = form_idx
                if tag in ('input', 'submit'):
                    self.forms[form_idx]['inputs'].append(el)
            
            elements.append(el)
        
        return elements

    def next_interactive(self):
        start = self.selected_index
        n = len(self.elements)
        for i in range(1, n+1):
            idx = (start + i) % n
            if self.elements[idx].is_interactive:
                old_selected = self.selected_index
                self.selected_index = idx
                
                # Auto-scroll to keep selected item visible using the new pixel-based system
                if hasattr(self, 'cached_display_lines') and self.cached_display_lines:
                    # Find which display line contains this element
                    target_line_idx = None
                    for line_idx, line_data in enumerate(self.cached_display_lines):
                        element_idx = line_data[2]  # element_idx is at index 2
                        if element_idx == idx:
                            target_line_idx = line_idx
                            break
                    
                    if target_line_idx is not None:
                        # Calculate line positions
                        line_positions = []
                        current_height = 0
                        for line in self.cached_display_lines:
                            line_positions.append(current_height)
                            line_height_actual = line[3] if len(line) > 3 else 6
                            current_height += line_height_actual
                        
                        # Get the target line's position
                        target_y = line_positions[target_line_idx]
                        screen_height = 192  # Approximate screen height - should get from context
                        
                        # Calculate current scroll position in pixels
                        current_scroll_pixels = self.scroll_offset * 6
                        
                        # Check if target is visible
                        if target_y < current_scroll_pixels:
                            # Target is above visible area - scroll up
                            self.scroll_offset = max(0, target_y // 6)
                        elif target_y >= current_scroll_pixels + screen_height:
                            # Target is below visible area - scroll down
                            desired_scroll = (target_y - screen_height + 12) // 6  # +12 for some margin
                            # Apply scroll bounds
                            total_height = current_height
                            max_scroll_pixels = max(0, total_height - screen_height + 6)
                            max_scroll_steps = max_scroll_pixels // 6
                            self.scroll_offset = min(max_scroll_steps, max(0, desired_scroll))
                
                # Track last selected input
                sel = self.elements[idx]
                if sel.tag == 'input':
                    self.last_selected_input = sel
                    if id(sel) not in self.input_buffers:
                        self.input_buffers[id(sel)] = sel.attrs.get('value', "")
                break

    def prev_interactive(self):
        start = self.selected_index
        n = len(self.elements)
        for i in range(1, n+1):
            idx = (start - i) % n
            if self.elements[idx].is_interactive:
                old_selected = self.selected_index
                self.selected_index = idx
                
                # Auto-scroll to keep selected item visible using the new pixel-based system
                if hasattr(self, 'cached_display_lines') and self.cached_display_lines:
                    # Find which display line contains this element
                    target_line_idx = None
                    for line_idx, line_data in enumerate(self.cached_display_lines):
                        element_idx = line_data[2]  # element_idx is at index 2
                        if element_idx == idx:
                            target_line_idx = line_idx
                            break
                    
                    if target_line_idx is not None:
                        # Calculate line positions
                        line_positions = []
                        current_height = 0
                        for line in self.cached_display_lines:
                            line_positions.append(current_height)
                            line_height_actual = line[3] if len(line) > 3 else 6
                            current_height += line_height_actual
                        
                        # Get the target line's position
                        target_y = line_positions[target_line_idx]
                        screen_height = 192  # Approximate screen height - should get from context
                        
                        # Calculate current scroll position in pixels
                        current_scroll_pixels = self.scroll_offset * 6
                        
                        # Check if target is visible
                        if target_y < current_scroll_pixels:
                            # Target is above visible area - scroll up
                            self.scroll_offset = max(0, target_y // 6)
                        elif target_y >= current_scroll_pixels + screen_height:
                            # Target is below visible area - scroll down
                            desired_scroll = (target_y - screen_height + 12) // 6  # +12 for some margin
                            # Apply scroll bounds
                            total_height = current_height
                            max_scroll_pixels = max(0, total_height - screen_height + 6)
                            max_scroll_steps = max_scroll_pixels // 6
                            self.scroll_offset = min(max_scroll_steps, max(0, desired_scroll))
                
                # Track last selected input
                sel = self.elements[idx]
                if sel.tag == 'input':
                    self.last_selected_input = sel
                    if id(sel) not in self.input_buffers:
                        self.input_buffers[id(sel)] = sel.attrs.get('value', "")
                break

    def get_selected(self):
        return self.elements[self.selected_index] if self.elements else None

    def generate_display_lines(self, max_text_width, font, get_text_size_func):
        """Generate wrapped display lines for all elements with proper height tracking"""
        display_lines = []
        element_line_map = {}  # Maps line index to element index
        
        # Reserve space for scrollbar if needed
        scrollbar_width = 3
        adjusted_width = max_text_width - scrollbar_width
        
        for i, el in enumerate(self.elements):
            color = 2 if el.is_interactive else 1
            text = f"[{el.tag.upper()}] {el.text}" if el.text else f"[{el.tag.upper()}]"
            
            if el.tag == 'input':
                buf = self.input_buffers.get(id(el), el.attrs.get('value', ''))
                if i == self.selected_index:
                    text = f"[INPUT] {buf}_"
                else:
                    text = f"[INPUT] {buf}"
            elif el.tag == 'submit':
                if i == self.selected_index:
                    text = f"[SUBMIT] {el.text}"
                else:
                    text = f"[SUBMIT] {el.text}"
            elif el.tag == 'a':
                if i == self.selected_index:
                    text = f"[LINK] {el.text}"
                else:
                    text = f"[LINK] {el.text}"
            elif el.tag in ('p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'text'):
                # Display non-interactive content without brackets
                text = el.text if el.text else ""
            elif el.tag == 'img':
                # Image element - display alt text or placeholder
                text = f"[IMG] {el.attrs.get('alt', 'Image')}"
            elif el.tag == 'br':
                # Line break - add empty line for spacing with special height marker
                text = ""
            else:
                text = text
            
            # Simple word wrapping (faster than pixel-perfect) with adjusted width
            max_chars = max(16, adjusted_width // 4)  # Rough estimate
            # Images should not be wrapped - they occupy exactly one display line
            if el.tag == 'img':
                wrapped_lines = [text]  # Single line for images, no wrapping
            else:
                wrapped_lines = self.simple_wrap_text(text, max_chars)
            
            # Add wrapped lines to display with height information
            for line_idx, line in enumerate(wrapped_lines):
                # Calculate height based on element type
                if el.tag == 'br':
                    height = 2  # br elements are 2px
                elif el.tag == 'img':
                    # Check if we have image data to get actual height
                    src = el.attrs.get('src', '')
                    resolved_url = self.resolve_image_url(src)
                    if resolved_url in self.image_cache and self.image_cache[resolved_url]['image'] is not None:
                        height = self.image_cache[resolved_url]['height'] + 2  # Add 2px padding
                    else:
                        height = 6  # Default text height while loading
                else:
                    height = 6  # Normal text elements are 6px
                
                is_selected = (i == self.selected_index)
                display_lines.append((line, color, i, height, is_selected))
                element_line_map[len(display_lines) - 1] = i
        
        return display_lines, element_line_map

    def simple_wrap_text(self, text, max_chars):
        """Simple character-based text wrapping for better performance"""
        if not text or len(text) <= max_chars:
            return [text] if text else [""]
        
        lines = []
        words = text.split(' ')
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " + word if current_line else word)
            if len(test_line) <= max_chars:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = word
                else:
                    # Word is too long, break it
                    while len(word) > max_chars:
                        lines.append(word[:max_chars])
                        word = word[max_chars:]
                    current_line = word
        
        if current_line:
            lines.append(current_line)
        
        return lines if lines else [""]

    # Not used in new system
    def render(self, surface, font):
        pass

    def resolve_image_url(self, src):
        """Resolve relative URLs to absolute URLs consistently"""
        if not src:
            return src
        
        if src.startswith('http'):
            return src
        
        base_url = getattr(self, 'base_url', 'http://frogfind.com')
        if src.startswith('/'):
            # Absolute path - use domain from base URL
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{src}"
        else:
            # Relative path
            return base_url.rstrip('/') + '/' + src.lstrip('/')

    def download_and_process_image(self, url, max_width=120, max_height=30):
        """Download and process an image for display"""
        print(f"[FrogFind] Attempting to download image: {url}")
        try:
            # Check if already cached and not just a loading placeholder
            if url in self.image_cache and not self.image_cache[url].get('loading', False):
                print(f"[FrogFind] Image already cached: {url}")
                return self.image_cache[url]
            
            processed = AppImageUtils.process_image_from_url(
                url,
                max_width=max_width,
                max_height=max_height,
            )
            print(
                f"[FrogFind] Processed image to {processed['width']}x{processed['height']}"
            )
            
            result = {
                **processed,
                'url': url,
                'loading': False
            }
            
            # Cache the result
            self.image_cache[url] = result
            print(f"[FrogFind] Successfully processed and cached image: {url}")
            return result
            
        except Exception as e:
            print(f"[FrogFind] Failed to download image {url}: {e}")
            # Return placeholder data
            placeholder = {
                'image': None,
                'width': 0,
                'height': 0,
                'url': url,
                'error': str(e),
                'loading': False
            }
            self.image_cache[url] = placeholder
            return placeholder

    def start_image_download(self, element, on_complete_callback=None):
        """Start downloading an image in the background"""
        if element.tag == 'img':
            src = element.attrs.get('src', '')
            if src:
                # Resolve URL consistently
                resolved_url = self.resolve_image_url(src)
                
                if resolved_url not in self.image_cache:
                    # Add placeholder to cache immediately to avoid duplicate downloads
                    self.image_cache[resolved_url] = {
                        'image': None,
                        'width': 0,
                        'height': 0,
                        'url': resolved_url,
                        'loading': True
                    }
                    
                    print(f"[FrogFind] Starting download for image: {resolved_url}")
                    
                    # Start download in background thread
                    def download_image():
                        try:
                            result = self.download_and_process_image(resolved_url)
                            print(f"[FrogFind] Image download completed: {resolved_url}")
                            # Force display refresh by clearing cached display lines
                            self.cached_display_lines = None
                            # Call the callback to trigger a redraw
                            if on_complete_callback:
                                on_complete_callback()
                        except Exception as e:
                            print(f"[FrogFind] Image download failed: {resolved_url} - {e}")
                            # Call the callback even on failure to refresh display
                            if on_complete_callback:
                                on_complete_callback()
                    
                    thread = threading.Thread(target=download_image)
                    thread.daemon = True
                    thread.start()


 # App class for ProxiTalk

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.url = "http://frogfind.com"
        self.url_history = []  # Stack to track visited URLs for back navigation
        self.shared_image_cache = {}  # Shared cache across all renderer instances
        self.renderer = None
        self.drawing = context["drawing"]  # Use new region-based drawing system
        self.font = context["fonts"]["small"]
        self.screen_width = context["screen_width"]
        self.screen_height = context["screen_height"]
        self.last_image_cache_size = 0  # Track cache changes to refresh display
        self.held_keys = context.get("pressed_keys", set())  # For continuous scroll
        self._last_scroll_time = 0
        self._scroll_repeat_delay = 0.4  # Initial delay before repeat (seconds)
        self._scroll_repeat_interval = 0.07  # Repeat rate (seconds)
        self._scrolling_direction = None

        # Loading state
        self.loading = False
        self.loading_url = ""
        self.loading_status = ""
        self._spinner_tick = 0

    def on_image_loaded(self):
        """Callback called when an image finishes loading"""
        if self.renderer:
            self.renderer.cached_display_lines = None
        self.draw()

    def fetch_page(self, url):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            html_text = resp.text
            self.save_html(url, html_text)
            return html_text
        except Exception as e:
            return f"<h1>Error</h1><p>{e}</p>"

    def save_html(self, url, html_text):
        save_dir = os.path.join(os.path.dirname(__file__), "visited_pages")
        os.makedirs(save_dir, exist_ok=True)
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        filename = os.path.join(save_dir, f"{url_hash}.html")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(html_text)
        except Exception:
            pass

    def _finish_navigation(self, url, html_text):
        """Called from fetch thread once HTML is ready."""
        self.url = url
        renderer = SimpleHTMLRenderer(html_text)
        renderer.base_url = url
        renderer.image_cache = self.shared_image_cache
        renderer.image_load_callback = self.on_image_loaded
        self.renderer = renderer
        self.loading = False
        self.loading_status = ""
        self.draw()

    def navigate_to_url(self, new_url, add_to_history=True):
        """Start async navigation to a new URL."""
        if add_to_history and self.url != new_url:
            self.url_history.append(self.url)

        self.loading = True
        self.loading_url = new_url
        self.loading_status = "Connecting..."
        self.draw()

        def fetch_worker():
            self.loading_status = "Loading page..."
            html_text = self.fetch_page(new_url)
            self._finish_navigation(new_url, html_text)

        threading.Thread(target=fetch_worker, daemon=True).start()

    def submit_form(self, method, action, data):
        """Start async form submission."""
        self.url_history.append(self.url)
        self.loading = True
        self.loading_url = action
        self.loading_status = "Submitting..."
        self.draw()

        def fetch_worker():
            self.loading_status = "Loading page..."
            try:
                if method == 'post':
                    resp = requests.post(action, data=data, timeout=10)
                else:
                    resp = requests.get(action, params=data, timeout=10)
                resp.raise_for_status()
                html_text = resp.text
                self.save_html(action, html_text)
            except Exception as e:
                html_text = f"<h1>Error</h1><p>{e}</p>"
            self._finish_navigation(action, html_text)

        threading.Thread(target=fetch_worker, daemon=True).start()

    def go_back(self):
        """Navigate back to the previous URL if available."""
        if self.url_history:
            self.navigate_to_url(self.url_history.pop(), add_to_history=False)
            return True
        return False

    def start(self):
        self.navigate_to_url(self.url, add_to_history=False)

    def update(self):
        # Animate spinner while loading
        if self.loading:
            self._spinner_tick += 1
            if self._spinner_tick % 2 == 0:
                self.draw()
            return

        if not self.renderer:
            return

        # Check if any images have finished loading
        current_cache_size = len([v for v in self.renderer.image_cache.values() if v.get('image') is not None])
        if current_cache_size != self.last_image_cache_size:
            self.last_image_cache_size = current_cache_size
            self.renderer.cached_display_lines = None
            self.draw()
        # Continuous scroll logic
        import time as _time
        now = _time.time()
        scroll_key = None
        if "KEY_UP" in self.held_keys:
            scroll_key = "KEY_UP"
            direction = -1
        elif "KEY_DOWN" in self.held_keys:
            scroll_key = "KEY_DOWN"
            direction = 1
        else:
            self._scrolling_direction = None
            self._last_scroll_time = 0
            return

        # Only scroll if not in input field
        selected = self.renderer.get_selected()
        if selected and selected.tag == 'input':
            self._scrolling_direction = None
            self._last_scroll_time = 0
            return

        # Initial press: delay, then repeat
        if self._scrolling_direction != direction:
            self._scrolling_direction = direction
            self._last_scroll_time = now
            # Do one scroll immediately
            self._do_scroll(direction)
            return

        delay = self._scroll_repeat_delay if self._last_scroll_time == now else self._scroll_repeat_interval
        if now - self._last_scroll_time >= delay:
            self._do_scroll(direction)
            self._last_scroll_time = now

    def _do_scroll(self, direction):
        if direction == -1:
            # Scroll up
            prev_offset = self.renderer.scroll_offset
            self.renderer.scroll_offset = max(0, self.renderer.scroll_offset - 1)
            if self.renderer.scroll_offset != prev_offset:
                self.draw()
        elif direction == 1:
            # Scroll down
            if hasattr(self.renderer, 'cached_display_lines') and self.renderer.cached_display_lines:
                total_height = 0
                for line in self.renderer.cached_display_lines:
                    line_height_actual = line[3] if len(line) > 3 else 6
                    total_height += line_height_actual
                max_scroll_pixels = max(0, total_height - self.screen_height + 6)
                max_scroll_steps = max_scroll_pixels // 6
                prev_offset = self.renderer.scroll_offset
                if self.renderer.scroll_offset < max_scroll_steps:
                    self.renderer.scroll_offset += 1
                    if self.renderer.scroll_offset != prev_offset:
                        self.draw()

    def onkeydown(self, keycode):
        if self.loading:
            return  # Ignore input while loading

        if keycode in ("KEY_ESC", "KEY_ESCAPE"):
            self.context["app_manager"].swap_app_async("frogfind_web", "launcher", update_rate_hz=20.0, delay=0.1)
            return

        if not self.renderer:
            return

        selected = self.renderer.get_selected()

        if keycode == "KEY_BACKSPACE":
            if selected and selected.tag == 'input':
                self.renderer.input_buffers[id(selected)] = self.renderer.input_buffers.get(id(selected), '')[:-1]
                self.draw()
            else:
                self.go_back()

        elif keycode in ("KEY_LEFTALT", "KEY_RIGHTALT"):
            self.renderer.next_interactive()
            self.draw()

        elif keycode == "KEY_UP":
            self.renderer.scroll_offset = max(0, self.renderer.scroll_offset - 1)
            self.draw()

        elif keycode == "KEY_DOWN":
            if self.renderer.cached_display_lines:
                total_height = sum(l[3] if len(l) > 3 else 6 for l in self.renderer.cached_display_lines)
                max_scroll_steps = max(0, total_height - self.screen_height + 6) // 6
                if self.renderer.scroll_offset < max_scroll_steps:
                    self.renderer.scroll_offset += 1
                    self.draw()

        elif keycode in ("KEY_ENTER", "KEY_RETURN"):
            if not selected:
                return
            if selected.tag == 'a':
                href = selected.attrs.get('href', '')
                if href:
                    if not href.startswith('http'):
                        href = self.url.rstrip('/') + '/' + href.lstrip('/')
                    self.navigate_to_url(href)
            elif selected.tag == 'input':
                buf = self.renderer.input_buffers.get(id(selected), '').strip()
                if buf:
                    self.navigate_to_url(buf if buf.startswith('http') else 'http://' + buf)
            elif selected.tag == 'submit':
                form_idx = getattr(selected, 'form_idx', None)
                if form_idx is not None and hasattr(self.renderer, 'forms'):
                    form = self.renderer.forms[form_idx]
                    data = {
                        el.attrs.get('name', 'input'): self.renderer.input_buffers.get(id(el), el.attrs.get('value', ''))
                        for el in form['inputs'] if el.tag == 'input'
                    }
                    method = form['attrs'].get('method', 'get').lower()
                    action = form['attrs'].get('action', self.url)
                    if not action.startswith('http'):
                        from urllib.parse import urlparse
                        parsed = urlparse(self.url)
                        action = f"{parsed.scheme}://{parsed.netloc}{action}" if action.startswith('/') else self.url.rstrip('/') + '/' + action.lstrip('/')
                    self.submit_form(method, action, data)
                else:
                    self.navigate_to_url(self.url, add_to_history=False)

        elif selected and selected.tag == 'input':
            char = key_map.get(keycode, "")
            if char:
                self.renderer.input_buffers[id(selected)] = self.renderer.input_buffers.get(id(selected), '') + char
                self.draw()

    def stop(self):
        pass
    
    def wrap_text(self, text, max_width, font):
        """Wrap text to fit within max_width pixels using ProxiTalk's text measurement"""
        if not text:
            return [""]
        
        # Check if the entire text fits
        text_width = self.context["get_text_size"](text, font)[0]
        if text_width <= max_width:
            return [text]
        
        lines = []
        words = text.split(' ')
        current_line = ""
        
        for word in words:
            # Test if adding this word would exceed the width
            test_line = current_line + (" " + word if current_line else word)
            test_width = self.context["get_text_size"](test_line, font)[0]
            
            if test_width > max_width:
                if current_line:  # If we have content on current line
                    lines.append(current_line)
                    current_line = word
                    # Check if single word is too long
                    word_width = self.context["get_text_size"](word, font)[0]
                    if word_width > max_width:
                        # Break long word into chunks
                        while word:
                            char_count = 1
                            while char_count <= len(word):
                                chunk = word[:char_count]
                                chunk_width = self.context["get_text_size"](chunk, font)[0]
                                if chunk_width > max_width:
                                    if char_count > 1:
                                        lines.append(word[:char_count-1])
                                        word = word[char_count-1:]
                                        break
                                    else:
                                        # Even single character is too wide, just add it
                                        lines.append(word[0])
                                        word = word[1:]
                                        break
                                char_count += 1
                            else:
                                # Entire remaining word fits
                                current_line = word
                                word = ""
                else:  # Word itself is too long and we have no current line
                    # Break the word character by character
                    while word:
                        char_count = 1
                        while char_count <= len(word):
                            chunk = word[:char_count]
                            chunk_width = self.context["get_text_size"](chunk, font)[0]
                            if chunk_width > max_width:
                                if char_count > 1:
                                    lines.append(word[:char_count-1])
                                    word = word[char_count-1:]
                                    break
                                else:
                                    # Even single character is too wide, just add it
                                    lines.append(word[0])
                                    word = word[1:]
                                    break
                            char_count += 1
                        else:
                            # Entire remaining word fits
                            current_line = word
                            word = ""
            else:
                current_line = test_line
        
        if current_line:
            lines.append(current_line)
        
        return lines if lines else [""]

    def _draw_loading(self):
        """Draw centered loading screen with animated spinner."""
        font = self.font
        line_height = 6
        spinner_chars = ["|", "/", "-", "\\"]
        spinner_char = spinner_chars[(self._spinner_tick // 2) % len(spinner_chars)]

        # Truncate URL to fit screen
        url_display = self.loading_url
        max_chars = (self.screen_width - 4) // 4
        if len(url_display) > max_chars:
            url_display = url_display[:max_chars - 3] + "..."

        lines = [self.loading_status, url_display]
        total_h = (len(lines) + 1) * line_height
        y = (self.screen_height - total_h) // 2

        for line in lines:
            if line:
                w = self.context["get_text_size"](line, font)[0]
                self.drawing["draw_text"](line, (self.screen_width - w) // 2, y, font)
            y += line_height

        spinner_text = f"[{spinner_char}]"
        w = self.context["get_text_size"](spinner_text, font)[0]
        self.drawing["draw_text"](spinner_text, (self.screen_width - w) // 2, y + 2, font)

    def draw(self):
        self.drawing["begin_batch"]()
        try:
            self.drawing["clear_screen"]()

            if self.loading:
                self._draw_loading()
                return

            if not self.renderer:
                return

            line_height = 6
            
            # Use actual screen width for wrapping, leaving small margin and left padding
            left_padding = 1
            max_text_width = self.screen_width - 4 - left_padding
            
            # Check if we need to regenerate display lines
            current_input_buffers_hash = hash(tuple(sorted(self.renderer.input_buffers.items())))
            needs_regeneration = (
                self.renderer.cached_display_lines is None or
                self.renderer.last_screen_width != max_text_width or
                self.renderer.last_selected_index != self.renderer.selected_index or
                self.renderer.last_input_buffers_hash != current_input_buffers_hash
            )
            
            if needs_regeneration:
                self.renderer.cached_display_lines, element_line_map = self.renderer.generate_display_lines(
                    max_text_width, self.font, self.context["get_text_size"]
                )
                self.renderer.last_screen_width = max_text_width
                self.renderer.last_selected_index = self.renderer.selected_index
                self.renderer.last_input_buffers_hash = current_input_buffers_hash
            
            display_lines = self.renderer.cached_display_lines
            
            # Calculate total content height and line positions
            line_positions = []
            current_height = 0
            for line in display_lines:
                line_positions.append(current_height)
                line_height_actual = line[3] if len(line) > 3 else 6  # Use stored height or default to 6
                current_height += line_height_actual
            
            total_content_height = current_height
            max_screen_height = self.screen_height
            
            # Calculate which lines are visible based on scroll offset
            if total_content_height <= max_screen_height:
                # All content fits on screen
                self.renderer.scroll_offset = 0
                visible_lines = list(range(len(display_lines)))
            else:
                # Need scrolling - convert scroll offset to pixel offset
                max_scroll_pixels = total_content_height - max_screen_height + 6  # +6px for extra line
                max_scroll_steps = max_scroll_pixels // 6  # Maximum scroll steps
                
                # Ensure scroll offset doesn't exceed bounds
                self.renderer.scroll_offset = min(max_scroll_steps, max(0, self.renderer.scroll_offset))
                
                scroll_pixels = self.renderer.scroll_offset * 6  # Current scroll in pixels
                
                # Find which lines are visible
                visible_lines = []
                for i, line_y in enumerate(line_positions):
                    line_height_actual = display_lines[i][3] if len(display_lines[i]) > 3 else 6
                    line_bottom = line_y + line_height_actual
                    
                    # Check if line overlaps with visible area
                    if line_bottom > scroll_pixels and line_y < scroll_pixels + max_screen_height:
                        visible_lines.append(i)
            
            # Draw visible lines
            current_y = 0
            drawn_images = set()  # Track which image elements we've already drawn
            for line_idx in visible_lines:
                if line_idx < len(display_lines):
                    line_data = display_lines[line_idx]
                    line_text, color, element_idx = line_data[0], line_data[1], line_data[2]
                    line_height_actual = line_data[3] if len(line_data) > 3 else 6
                    is_selected = line_data[4] if len(line_data) > 4 else False
                    
                    # Adjust y position based on scroll
                    line_y = line_positions[line_idx]
                    scroll_pixels = self.renderer.scroll_offset * 6
                    adjusted_y = line_y - scroll_pixels
                    
                    # Only draw if any part of the line or image is visible
                    is_img = (element_idx < len(self.renderer.elements) and self.renderer.elements[element_idx].tag == 'img')
                    img_height = None
                    if is_img and element_idx < len(self.renderer.elements):
                        src = self.renderer.elements[element_idx].attrs.get('src', '')
                        resolved_url = self.renderer.resolve_image_url(src)
                        if resolved_url in self.renderer.image_cache:
                            img_data = self.renderer.image_cache[resolved_url]
                            if img_data['image'] is not None:
                                img_height = img_data['height']
                    if (
                        (not is_img and adjusted_y >= 0 and adjusted_y < max_screen_height)
                        or (is_img and img_height is not None and adjusted_y + img_height > 0 and adjusted_y < max_screen_height)
                    ):
                        # Check if this is a line break element
                        if (element_idx < len(self.renderer.elements) and 
                            self.renderer.elements[element_idx].tag == 'br'):
                            # For <br> tags, just advance position (no text drawing)
                            pass
                        elif (element_idx < len(self.renderer.elements) and 
                              self.renderer.elements[element_idx].tag == 'img'):
                            # Handle image element - only draw once per element
                            if element_idx not in drawn_images:
                                drawn_images.add(element_idx)
                                img_element = self.renderer.elements[element_idx]
                                src = img_element.attrs.get('src', '')
                                resolved_url = self.renderer.resolve_image_url(src)
                                
                                if resolved_url in self.renderer.image_cache:
                                    img_data = self.renderer.image_cache[resolved_url]
                                    if img_data['image'] is not None:
                                        # Draw the actual image, cropping if needed
                                        img_width = img_data['width']
                                        img_height = img_data['height']
                                        x_offset = left_padding + (max_text_width - 3 - img_width) // 2  # Center the image (3 = scrollbar width)
                                        
                                        # Determine cropping for top and bottom
                                        crop_top = 0
                                        crop_bottom = img_height
                                        draw_y = adjusted_y
                                        # If image starts above the visible area
                                        if adjusted_y < 0:
                                            crop_top = -adjusted_y
                                            draw_y = 0
                                        # If image extends below the visible area
                                        if adjusted_y + (crop_bottom - crop_top) > max_screen_height:
                                            crop_bottom = crop_top + (max_screen_height - draw_y)
                                        visible_height = crop_bottom - crop_top
                                        # Only draw if some part is visible
                                        if visible_height > 0:
                                            img_to_draw = img_data['image']
                                            if crop_top > 0 or crop_bottom < img_height:
                                                # Convert to 'L' before cropping, then back to '1' for display
                                                img_to_draw = img_to_draw.convert('L').crop((0, crop_top, img_width, crop_bottom)).convert('1', dither=Image.Dither.FLOYDSTEINBERG)
                                            # Clear the image area with background
                                            if is_selected:
                                                self.drawing["draw_area"](x_offset-1, draw_y-1, img_width + 2, visible_height + 2, 255)
                                            else:
                                                self.drawing["draw_area"](x_offset, draw_y, img_width, visible_height, 0)
                                            # Draw the cropped image
                                            self.drawing["draw_image"](img_to_draw, x_offset, draw_y)
                                            print(f"[FrogFind] Drew (cropped) image {resolved_url} at ({x_offset}, {draw_y}) - element {element_idx}, line {line_idx}, crop_top={crop_top}, crop_bottom={crop_bottom}")
                                    elif img_data.get('loading', False):
                                        # Image still loading, show placeholder
                                        placeholder_text = f"[IMG LOADING: {img_element.attrs.get('alt', 'Image')}]"
                                        if is_selected:
                                            text_width = self.context["get_text_size"](placeholder_text, self.font)[0]
                                            self.drawing["draw_area"](left_padding-1, adjusted_y-1, text_width + 2, line_height_actual, 255)
                                            self.drawing["draw_text"](placeholder_text, left_padding, adjusted_y, self.font, 0)
                                        else:
                                            self.drawing["draw_text"](placeholder_text, left_padding, adjusted_y, self.font, 2)  # Blue for loading
                                    else:
                                        # Image failed to load, show error text
                                        error_text = f"[IMG ERROR: {img_data.get('error', 'Failed to load')}]"
                                        if is_selected:
                                            text_width = self.context["get_text_size"](error_text, self.font)[0]
                                            self.drawing["draw_area"](left_padding-1, adjusted_y-1, text_width + 2, line_height_actual, 255)
                                            self.drawing["draw_text"](error_text, left_padding, adjusted_y, self.font, 0)
                                        else:
                                            self.drawing["draw_text"](error_text, left_padding, adjusted_y, self.font, 1)  # Gray for errors
                                else:
                                    # Image not in cache yet, show placeholder
                                    placeholder_text = f"[IMG LOADING: {img_element.attrs.get('alt', 'Image')}]"
                                    if is_selected:
                                        text_width = self.context["get_text_size"](placeholder_text, self.font)[0]
                                        self.drawing["draw_area"](left_padding-1, adjusted_y-1, text_width + 2, line_height_actual, 255)
                                        self.drawing["draw_text"](placeholder_text, left_padding, adjusted_y, self.font, 0)
                                    else:
                                        self.drawing["draw_text"](placeholder_text, left_padding, adjusted_y, self.font, 2)  # Blue for loading
                            # If this is a subsequent line of the same image element, skip drawing
                        else:
                            # Draw selection background for selected elements
                            if is_selected and line_text.strip():
                                # Calculate text width for background
                                text_width = self.context["get_text_size"](line_text, self.font)[0]
                                # Draw white background rectangle
                                self.drawing["draw_area"](left_padding-1, adjusted_y-1, text_width + 2, line_height_actual, 255)
                                # Draw black text on white background
                                self.drawing["draw_text"](line_text, left_padding, adjusted_y, self.font, 0)
                            else:
                                # Normal text drawing with left padding
                                self.drawing["draw_text"](line_text, left_padding, adjusted_y, self.font, color)
            
            # Draw vertical scrollbar if there are more lines than can fit
            if total_content_height > max_screen_height:
                scrollbar_x = self.screen_width - 3  # Position at right edge
                scrollbar_top = 1
                scrollbar_bottom = self.screen_height - 1
                scrollbar_height = scrollbar_bottom - scrollbar_top
                
                # Calculate scrollbar position based on scroll_offset
                max_scroll_pixels = total_content_height - max_screen_height + 6  # +6px for extra line
                scroll_pixels = self.renderer.scroll_offset * 6
                
                if max_scroll_pixels > 0:
                    # Calculate the position of the scroll indicator
                    scroll_ratio = min(1.0, scroll_pixels / max_scroll_pixels)
                    
                    # Calculate indicator position
                    indicator_height = max(2, scrollbar_height // 10)  # At least 2px tall
                    usable_height = scrollbar_height - indicator_height
                    indicator_y = scrollbar_top + int(scroll_ratio * usable_height)
                    
                    # Draw scrollbar background (light gray track)
                    self.drawing["draw_area"](scrollbar_x + 2, scrollbar_top, 1, scrollbar_height, 255)
                    
                    # Draw scroll indicator (dark gray/black)
                    self.drawing["draw_area"](scrollbar_x, indicator_y, 2, indicator_height, 255)
                
        finally:
            self.drawing["end_batch"]()