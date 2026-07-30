import os
import time
from typing import List

from interfaces import AppBase
from utils.image_utils import AppImageUtils

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.drawing = context["drawing"]
        self.font_small = context["fonts"]["small"]
        self.font_default = context["fonts"]["default"]
        self.width = context["screen_width"]
        self.height = context["screen_height"]
        self.tts = context["tts"]["run"]
        self.gallery_dir = context["FILES_DIR"]
        os.makedirs(self.gallery_dir, exist_ok=True)

        self.images: List[str] = []
        self.processed_cache = {}
        self.current_index = 0
        self.status_message = f"Drop PNG/JPG files into {self.gallery_dir}."
        self.needs_redraw = True

    def start(self):
        self.drawing["clear_screen"]()

        self.rescan_images()
        self.render()

    def update(self):
        advanced = self._update_animation()
        if self.needs_redraw or advanced:
            self.render()

    def rescan_images(self):
        candidates = []
        for entry in sorted(os.listdir(self.gallery_dir)):
            full_path = os.path.join(self.gallery_dir, entry)
            if os.path.isfile(full_path) and entry.lower().endswith(SUPPORTED_EXTENSIONS):
                candidates.append(full_path)

        previous_path = self.current_image_path()
        self.images = candidates
        if self.images:
            if previous_path in self.images:
                self.current_index = self.images.index(previous_path)
            else:
                self.current_index = min(
                    self.current_index, len(self.images) - 1)
        else:
            self.current_index = 0

        # Drop cache entries for removed files
        self.processed_cache = {
            path: data for path, data in self.processed_cache.items() if path in self.images}

        if not self.images:
            self.status_message = "No images found. Add files to gallery_images."
        else:
            self.status_message = f"Loaded {len(self.images)} image(s)."

        self.needs_redraw = True

    def current_image_path(self):
        if not self.images:
            return None
        return self.images[self.current_index]

    def current_cached_image(self):
        path = self.current_image_path()
        if not path:
            return None
        return self.processed_cache.get(path)

    def load_processed_image(self):
        path = self.current_image_path()
        if not path:
            return None

        cached = self.processed_cache.get(path)
        if cached:
            return cached

        try:
            image = AppImageUtils.load_image_from_file(path)
            if getattr(image, "is_animated", False):
                image.seek(0)
                animation = AppImageUtils.prepare_animation_frames(
                    image,
                    max_width=self.width,
                    max_height=self.height - 12,
                )
                processed = {
                    "type": "animated",
                    **animation,
                    "current_frame": 0,
                    "last_frame_time": time.time(),
                }
                self.status_message = f"Animating {os.path.basename(path)}."
            else:
                static = AppImageUtils.prepare_image_for_display(
                    image,
                    max_width=self.width,
                    max_height=self.height - 12,
                )
                processed = {"type": "static", **static}
                self.status_message = f"Showing {os.path.basename(path)}."

            self.processed_cache[path] = processed
            return processed
        except Exception as exc:
            self.status_message = f"Failed to load {os.path.basename(path)}."
            print(f"[Gallery] Unable to load {path}: {exc}")
            return None

    def render(self):
        footer_lines = self.footer_lines()
        footer_height = self._footer_height(footer_lines)
        
        if(self.needs_redraw):
            self.draw_footer(footer_lines, footer_height)
        self.render_image(footer_height)

    def render_image(self, footer_height=12):
        image_data = self.load_processed_image()

        if image_data:
            img = self._frame_for_display(image_data)
            if img:
                
                img_width = image_data["width"]
                img_height = image_data["height"]
                x = max(0, (self.width - img_width) // 2)
                available_height = max(0, self.height - footer_height)
                y = max(0, (available_height - img_height) // 2)
                
                # clear first to avoid ghosting
                self.drawing["clear_area"](x, y, img_width, img_height)
                self.drawing["draw_image"](img, x, y)
            else:
                self.drawing["draw_text"]("(Image unavailable)", 2, 2, self.font_default)
        else:
            # Reserve the main canvas for the help text if nothing to show
            self.drawing["draw_text"]("Gallery", 2, 2, self.font_default)

        self.needs_redraw = False

    def draw_footer(self, lines, footer_height):
        footer_y = max(0, self.height - footer_height)
        self.drawing["draw_area"](0, footer_y, self.width, footer_height, 0)

        line_height = 6
        for idx, text in enumerate(lines):
            y = footer_y + (idx * line_height)
            self.draw_centered_text(text, y)

    def _footer_height(self, lines):
        line_height = 6
        total_lines = max(1, len(lines))
        return max(line_height * total_lines, 6)

    def _frame_for_display(self, image_data):
        if image_data.get("type") == "animated":
            frames = image_data.get("frames", [])
            if not frames:
                return None
            frame_index = image_data.get("current_frame", 0) % len(frames)
            return frames[frame_index]
        return image_data.get("image")

    def _update_animation(self):
        image_data = self.current_cached_image()
        if not image_data or image_data.get("type") != "animated":
            return False

        frames = image_data.get("frames", [])
        durations = image_data.get("durations", [])
        if not frames or not durations:
            return False

        now = time.time()
        last_time = image_data.get("last_frame_time", now)
        elapsed_ms = (now - last_time) * 1000.0
        frame_index = image_data.get("current_frame", 0) % len(frames)
        frame_duration = durations[frame_index % len(durations)]

        if elapsed_ms >= frame_duration:
            image_data["current_frame"] = (frame_index + 1) % len(frames)
            image_data["last_frame_time"] = now
            return True

        return False

    def footer_lines(self):
        if not self.images:
            guidance = f"Add PNG/JPG to {self.gallery_dir}"
            return [guidance, "Left/Right: browse"]

        name = os.path.basename(self.current_image_path())
        position = f"{self.current_index + 1}/{len(self.images)}"
        info_line = self.shorten(f"{name} ({position})")
        return [info_line]

    def draw_centered_text(self, text, y):
        width, _ = self.context["get_text_size"](text, self.font_small)
        x = max(0, (self.width - width) // 2)
        self.drawing["draw_text"](text, x, y, self.font_small)

    @staticmethod
    def shorten(text, limit=26):
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def onkeyup(self, keycode):
        if keycode == "KEY_RIGHT" or keycode == "KEY_D":            
            self.advance(1)
        elif keycode == "KEY_LEFT" or keycode == "KEY_A":
            self.advance(-1)
        elif keycode == "KEY_R":
            self.rescan_images()
        elif keycode == "KEY_ENTER":
            self.describe_current()
        elif keycode == "KEY_ESC":
            self.exit_to_launcher()

    def advance(self, delta):
        if not self.images:
            return
        self.current_index = (self.current_index + delta) % len(self.images)
        self.drawing["clear_screen"]()
        self.needs_redraw = True

    def describe_current(self):
        path = self.current_image_path()
        if not path:
            return
        description = f"Showing {os.path.basename(path)}"
        self.tts(description, background=True)

    def exit_to_launcher(self):
        self.context["app_manager"].swap_app_async("gallery", "launcher", update_rate_hz=20.0, delay=0.1)

    def stop(self):
        pass
