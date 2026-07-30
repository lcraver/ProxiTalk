"""File Browser — navigate the device's whole filesystem (not just the
`files/` folder), preview text and image files, and rename/delete entries.

Every mode is one Column([content(header), fill(body)]) run through
ui.layout_root — same shape as proxi/app_settings — so the body (menu,
scroll_panel, image, or text_field) always gets exactly the space left
under the header, however tall that header's title happens to measure,
instead of hand-computed x/y/width/height. The header is just the current
path -- no keybinding hint line, so the body (the actual file list) keeps
as much of the 64px-tall display as possible.

Single ui.Menu drives the whole "list" mode (folders first, then files,
sorted -- see files.list_dir); ENTER descends into a folder or opens a
file's preview, R/X rename or delete whichever row is currently
highlighted (no separate actions sub-menu -- same flat "act on the
highlighted row" shape as app_settings' toggle-in-place, just three keys
instead of one). ESC/BACKSPACE steps up a directory; H jumps straight back
to the `files/` folder from wherever navigation has wandered off to.
Navigation starts at files.root_dir() (the `files/` folder) but ".." keeps
working past it all the way up to files.filesystem_root() (the drive root
on Windows, "/" on POSIX) -- there's no sandbox boundary apps/file_browser
itself enforces, matching any other on-device file manager."""

from __future__ import annotations

import os
import time

from core_os.apps_runtime.app_base import AppBase

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac"}
_CODE_EXTS = {".py", ".js", ".json", ".ini", ".cfg", ".yaml", ".yml", ".c", ".cpp", ".h", ".java", ".html", ".css", ".sh", ".ts"}
_TEXT_ICON_EXTS = {".txt", ".md", ".csv", ".log"}
_TEXT_EXTS = _CODE_EXTS | _TEXT_ICON_EXTS
_PREVIEW_MAX_BYTES = 4096

_UP_VALUE = "__up__"

_MODE_LIST = "list"
_MODE_PREVIEW = "preview"
_MODE_AUDIO = "audio"
_MODE_RENAME = "rename"

_AUDIO_STATUS_INTERVAL = 0.5
_AUDIO_JOG_SECONDS = 5.0
_AUDIO_END_EPSILON = 0.25

_ROOT_MARGIN = 2
_ROOT_SPACING = 2
_ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")
_ICON_SIZE = 9
_ICON_CATEGORIES = ("folder", "image", "video", "audio", "code", "text", "up", "misc")


class _PathHeader:
    """Right-aligned single-line path: `prefix` drawn as plain white-on-
    black text, `current` (just the current folder's own name, no
    ancestors) highlighted right after it with a solid halo -- same look
    as a selected Menu row -- so only the folder you're actually IN is
    highlighted, not the whole breadcrumb.

    Draws the halo manually (ink_bbox + a symmetric pad on all 4 sides)
    rather than via display_gfx.draw_text_inverted's own built-in
    highlighting -- that one clamps to never extend above/left of the
    (x, y) it's given (guarding a caller sitting flush at a hard edge),
    which for text that's already flush at its own top-left (true here:
    `current` starts right where `prefix` ends, with nothing above it)
    zeroes the top/left padding while keeping it on bottom/right, i.e. an
    asymmetric halo that reads as shifted down-right -- same failure mode
    documented on Menu.SELECTED_HALO_PADDING, which draws its own halo
    for the exact same reason. A private leaf widget (same shape as
    ui_test's _Swatch) rather than a general ui.py addition since nothing
    else needs this yet."""

    _HALO_PADDING = 1

    def __init__(self, gfx, prefix: str, current: str, font) -> None:
        self._gfx = gfx
        self.prefix = prefix
        self.current = current
        self.font = font
        self.x = self.y = self.width = self.height = 0

    def measure(self, available_w, available_h):
        text = self.prefix + self.current
        return (available_w, self._gfx["line_height"](text, self.font))

    def set_bounds(self, x, y, width, height):
        self.x, self.y, self.width, self.height = x, y, width, height

    def draw(self):
        self._gfx["clear_area"](self.x, self.y, self.width, self.height)
        if not self.prefix and not self.current:
            return
        prefix_w, _ = self._gfx["get_text_size"](self.prefix, self.font) if self.prefix else (0, 0)
        current_w, _ = self._gfx["get_text_size"](self.current, self.font) if self.current else (0, 0)
        total_w = prefix_w + current_w
        start_x = max(self.x, self.x + self.width - total_w)
        if self.prefix:
            self._gfx["draw_text"](self.prefix, start_x, self.y, font=self.font)
        if self.current:
            current_x = start_x + prefix_w
            p = self._HALO_PADDING
            ink_left, _, ink_w, ink_h = self._gfx["ink_bbox"](self.current, self.font)
            self._gfx["draw_area"](current_x + ink_left - p, self.y - p, ink_w + 2 * p, ink_h + 2 * p, fill=255)
            self._gfx["draw_text"](self.current, current_x, self.y, font=self.font, fill=0)

    def handle_key(self, keycode):
        return False


def _human_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{int(size)}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}GB"


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.context = context
        self.gfx = context["display_gfx"]
        self.ui = context["ui"]
        self.files = context["files"]
        self.images = context["images"]
        self.language = context["language"]
        self.input = context["input"]
        self.audio = context["audio"]
        self.app_control = context["app_control"]
        self.screen_width = context["screen_width"]

        self.current_dir = self.files["root_dir"]()
        self.mode = _MODE_LIST
        self.entries = []
        self.menu = None
        self.text_field = None
        self.image_widget = None
        self._preview_panel = None
        self._preview_entry_name = None
        self._dialog = None
        self._rename_entry = None
        self._audio_path = None
        self._audio_duration = 0.0
        self._audio_status_label = None
        self._audio_progress_bar = None
        self._audio_status_elapsed = 0.0
        self._last_update_time = None
        # Loaded once (display-ready '1'-mode PIL images, see images.load_file)
        # and reused as every matching MenuItem's icon -- a scrolling list can
        # have dozens of rows sharing the same 5 category icons, so decoding
        # per row per frame would be wasteful; ui.Menu just blits whichever
        # object each MenuItem already carries.
        self._category_icons = {
            category: self.images["load_file"](
                os.path.join(_ICON_DIR, f"{category}.png"), max_width=_ICON_SIZE, max_height=_ICON_SIZE
            )["image"]
            for category in _ICON_CATEGORIES
        }

    def start(self):
        print("[File Browser] Started")
        self._enter_list()

    # --- shared layout -------------------------------------------------------

    def _title(self):
        return self.current_dir

    def _clip_path_start(self, text, max_width, font):
        """Truncate `text` from the FRONT (with a leading "...") once it's
        wider than max_width, keeping the tail -- the opposite end from
        Menu._clip_label's trailing-ellipsis. The immediate/current folder
        (the tail of an absolute path) is what you actually care about
        while navigating; the drive letter and distant ancestors at the
        front are the least useful part to lose screen space to."""
        if not text or self.gfx["get_text_size"](text, font)[0] <= max_width:
            return text
        ellipsis = "..."
        while text and self.gfx["get_text_size"](ellipsis + text, font)[0] > max_width:
            text = text[1:]
        return ellipsis + text if text else ellipsis

    def _split_current_folder(self, path):
        """(prefix, current_name) -- current_name is just the folder we're
        actually in (path's last segment), prefix is everything before it
        (with its trailing separator kept, so prefix + current_name
        reconstructs `path`)."""
        trimmed = path.rstrip(os.sep) or path
        current_name = os.path.basename(trimmed)
        if not current_name:
            return "", trimmed
        return trimmed[: -len(current_name)], current_name

    def _header(self):
        small = self.gfx["fonts"]["small"]
        available_w = max(0, self.screen_width - 2 * _ROOT_MARGIN)
        prefix, current_name = self._split_current_folder(self._title())
        current_w, _ = self.gfx["get_text_size"](current_name, small)
        clipped_prefix = self._clip_path_start(prefix, max(0, available_w - current_w), small)
        # _PathHeader, not ui["label"] -- highlights just the folder we're
        # actually in with a solid halo (same look as a selected Menu row),
        # leaving the rest of the breadcrumb plain; still right-aligned, so
        # once the path is too long the visible tail (the current folder)
        # hugs the right edge rather than sitting wherever the (already
        # front-truncated) prefix happens to end.
        return _PathHeader(self.gfx, clipped_prefix, current_name, small)

    def _render(self, body):
        fill, content = self.ui["fill"], self.ui["content"]
        root = self.ui["column"]([content(self._header()), fill(body)], margin=_ROOT_MARGIN, spacing=_ROOT_SPACING)
        self.ui["layout_root"](root)

    # --- entry type icons --------------------------------------------------

    def _icon_category(self, entry):
        if entry is None:
            return None
        if entry["is_dir"]:
            return "folder"
        ext = os.path.splitext(entry["name"])[1].lower()
        if ext in _IMAGE_EXTS:
            return "image"
        if ext in _VIDEO_EXTS:
            return "video"
        if ext in _AUDIO_EXTS:
            return "audio"
        if ext in _CODE_EXTS:
            return "code"
        if ext in _TEXT_ICON_EXTS:
            return "text"
        return "misc"

    def _icon_for(self, entry):
        category = self._icon_category(entry)
        return self._category_icons.get(category) if category else None

    # --- list mode -----------------------------------------------------------

    def _enter_list(self, select_name=None):
        self.mode = _MODE_LIST
        self.text_field = None
        self.image_widget = None
        self._preview_panel = None

        self.entries = self.files["list_dir"](self.current_dir)
        items = []
        if self.files["parent_of"](self.current_dir) is not None:
            items.append(self.ui["menu_item"]("../", value=_UP_VALUE, icon=self._category_icons["up"]))
        for entry in self.entries:
            if entry["is_dir"]:
                label = f"{entry['name']}/"
            else:
                label = f"{entry['name']} ({_human_size(entry['size'])})"
            items.append(self.ui["menu_item"](label, value=entry["name"], icon=self._icon_for(entry)))

        if not items:
            self.menu = None
            body = self.ui["label"](self.language["t"]("file_browser.empty"), font=self.gfx["fonts"]["small"], align="center")
            self._render(body)
            return

        # padding=0 -- every px of the menu's own box goes to actual rows
        # instead of an inset margin around them, so the list packs as many
        # whole rows into the display as will actually fit.
        self.menu = self.ui["menu"](items, on_select=self._on_select, padding=0, margin=0)

        # _render() (via layout_root's fill()) is what actually resizes the
        # menu to its real on-screen height -- before this it's still
        # sitting at make_menu's full-display default. set_selected_index()
        # has to run AFTER that, not before: it snaps scroll to whatever
        # _target_scroll() computes from self.height at the time it's
        # called, so calling it against the pre-layout (too-tall) height
        # always concluded "the whole list already fits, no scroll needed"
        # -- selection moved to the right row but the list stayed scrolled
        # to the top, leaving that row off-screen whenever going up a
        # directory selected something below the first screenful.
        self._render(self.menu)

        if select_name is not None:
            for index, item in enumerate(items):
                if item.value == select_name:
                    self.menu.set_selected_index(index)
                    self.menu.draw()
                    break

    def _entry_for_item(self, item):
        if item is None or item.value == _UP_VALUE:
            return None
        for entry in self.entries:
            if entry["name"] == item.value:
                return entry
        return None

    def _selected_entry(self):
        return self._entry_for_item(self.menu.selected_item) if self.menu is not None else None

    def _go_up(self):
        parent = self.files["parent_of"](self.current_dir)
        if parent is None:
            self.app_control.swap_app_async("file_browser", "launcher", delay=0.1)
            return
        select_name = os.path.basename(self.current_dir.rstrip(os.sep))
        self.current_dir = parent
        self._enter_list(select_name=select_name)

    def _on_select(self, item):
        if item.value == _UP_VALUE:
            self._go_up()
            return
        entry = self._selected_entry()
        if entry is None:
            return
        if entry["is_dir"]:
            self.current_dir = os.path.join(self.current_dir, entry["name"])
            self._enter_list()
        else:
            self._enter_preview(entry)

    def _onkeydown_list(self, keycode):
        if keycode in ("KEY_ESC", "KEY_BACKSPACE"):
            self._go_up()
            return

        if keycode == "KEY_H":
            self.current_dir = self.files["root_dir"]()
            self._enter_list()
            return

        if self.menu is None:
            return

        if keycode == "KEY_R":
            entry = self._selected_entry()
            if entry is not None:
                self._enter_rename(entry)
            return

        if keycode == "KEY_X":
            entry = self._selected_entry()
            if entry is not None:
                self._confirm_delete(entry)
            return

        self.menu.handle_key(keycode)

    def _confirm_delete(self, entry):
        title = self.language["t"]("file_browser.delete.title")
        message = self.language["t"]("file_browser.delete.message").format(name=entry["name"])

        def _on_yes():
            abs_path = os.path.join(self.current_dir, entry["name"])
            try:
                self.files["delete"](abs_path)
            except OSError:
                self.ui["toast"]().error(self.language["t"]("file_browser.error.delete"))
            self._enter_list()

        def _on_no():
            self._enter_list()

        self._dialog = self.ui["dialog"](title, message, on_yes=_on_yes, on_no=_on_no)

    # --- preview mode ----------------------------------------------------

    def _enter_preview(self, entry):
        abs_path = os.path.join(self.current_dir, entry["name"])
        ext = os.path.splitext(entry["name"])[1].lower()
        self._preview_entry_name = entry["name"]

        if ext in _AUDIO_EXTS:
            self._enter_audio(entry, abs_path)
            return

        self.mode = _MODE_PREVIEW

        if ext in _IMAGE_EXTS:
            self.image_widget = self.ui["image"](abs_path, size="fill")
            self._preview_panel = None
            self._render(self.image_widget)
            return

        self.image_widget = None
        if ext in _TEXT_EXTS:
            result = self.files["read_text"](abs_path, max_bytes=_PREVIEW_MAX_BYTES)
        else:
            result = None

        if result is None:
            text = self.language["t"]("file_browser.no_preview")
        else:
            text = result["text"]
            if result["truncated"]:
                text += "\n..."

        self._preview_panel = self.ui["scroll_panel"](text=text)
        self._render(self._preview_panel)

    def _onkeydown_preview(self, keycode):
        if keycode in ("KEY_ESC", "KEY_BACKSPACE"):
            self._enter_list(select_name=self._preview_entry_name)
            return
        if self._preview_panel is not None:
            self._preview_panel.handle_key(keycode)

    # --- audio playback ---------------------------------------------------

    @staticmethod
    def _format_time(seconds):
        minutes, seconds = divmod(int(max(0.0, seconds)), 60)
        return f"{minutes}:{seconds:02d}"

    def _refresh_audio_ui(self):
        info = self.audio["get_stream_info"]()
        state_key = "file_browser.audio.paused" if info["is_paused"] else "file_browser.audio.playing"
        self._audio_status_label.set_text(self.language["t"](state_key))
        self._audio_status_label.draw()
        position = info["current_position"]
        progress = (position / self._audio_duration) if self._audio_duration > 0 else 0.0
        self._audio_progress_bar.set_progress(progress)
        self._audio_progress_bar.set_value_text(f"{self._format_time(position)}/{self._format_time(self._audio_duration)}")

    def _enter_audio(self, entry, abs_path):
        self.mode = _MODE_AUDIO
        self._audio_path = abs_path
        self._audio_status_elapsed = 0.0
        self._audio_duration = self.audio["get_duration"](abs_path)
        if not self.audio["start_stream"](abs_path):
            self.ui["toast"]().error(self.language["t"]("file_browser.error.audio"))
            self._enter_list()
            return

        small = self.gfx["fonts"]["small"]
        content = self.ui["content"]
        name_label = self.ui["label"](entry["name"], font=small)
        # Real placeholder text up front, not "" -- layout_root measures
        # every widget's height once, right here, and an empty Label
        # measures near-zero; set_text()-ing it to the real status
        # AFTER that initial layout doesn't redo the layout pass, so the
        # column had already given the progress bar right after it almost
        # no gap, and the two drew on top of each other.
        self._audio_status_label = self.ui["label"](self.language["t"]("file_browser.audio.playing"), font=small)
        self._audio_progress_bar = self.ui["progress_bar"](value_text="0:00/0:00")
        body = self.ui["column"](
            [content(name_label), content(self._audio_status_label), content(self._audio_progress_bar)],
            spacing=2,
        )
        self._render(body)
        self._refresh_audio_ui()

    def _seek_audio(self, delta):
        if self._audio_duration <= 0:
            return
        info = self.audio["get_stream_info"]()
        was_paused = info["is_paused"]
        # Never seek to the literal end -- that leaves zero PCM frames to
        # play, which the stream thread (reasonably) treats as "playback
        # already finished" and resets position back to 0, making a jog
        # that lands exactly on the last frame look like it silently
        # jumped back to the start instead of just... being at the end.
        seek_limit = max(0.0, self._audio_duration - _AUDIO_END_EPSILON)
        target = max(0.0, min(seek_limit, info["current_position"] + delta))
        self.audio["start_stream"](self._audio_path, start_offset=target)
        if was_paused:
            self.audio["pause_stream"]()
        self._refresh_audio_ui()

    def _onkeydown_audio(self, keycode):
        if keycode in ("KEY_ESC", "KEY_BACKSPACE"):
            self.audio["stop_stream"]()
            self._enter_list(select_name=self._preview_entry_name)
            return
        if keycode == "KEY_ENTER":
            if self.audio["is_stream_paused"]():
                self.audio["resume_stream"]()
            else:
                self.audio["pause_stream"]()
            self._refresh_audio_ui()
            return
        if keycode == "KEY_LEFT":
            self._seek_audio(-_AUDIO_JOG_SECONDS)
            return
        if keycode == "KEY_RIGHT":
            self._seek_audio(_AUDIO_JOG_SECONDS)
            return

    # --- rename mode -----------------------------------------------------

    def _enter_rename(self, entry):
        self.mode = _MODE_RENAME
        self._rename_entry = entry

        text_input = self.input["make_text_input"]()
        text_input.on_submit = self._on_rename_submit
        text_input.on_cancel = lambda: self._enter_list(select_name=entry["name"])
        self.text_field = self.ui["text_field"](text_input, font=self.gfx["fonts"]["small"], valign="center")
        self._render(self.text_field)

    def _on_rename_submit(self, new_name):
        entry = self._rename_entry
        abs_path = os.path.join(self.current_dir, entry["name"])
        try:
            self.files["rename"](abs_path, new_name)
            self._enter_list(select_name=new_name)
        except (OSError, ValueError):
            self.ui["toast"]().error(self.language["t"]("file_browser.error.rename"))
            self._enter_list(select_name=entry["name"])

    def _onkeydown_rename(self, keycode):
        if self.text_field is not None:
            self.text_field.handle_key(keycode)

    # --- app lifecycle ---------------------------------------------------

    def update(self):
        now = time.monotonic()
        dt = 0.0 if self._last_update_time is None else now - self._last_update_time
        self._last_update_time = now
        if self.mode == _MODE_LIST and self.menu is not None:
            self.menu.tick(dt)
        elif self.mode == _MODE_PREVIEW and self.image_widget is not None:
            self.image_widget.update(dt)
        elif self.mode == _MODE_AUDIO and self._audio_status_label is not None:
            # Only the elapsed-time text/progress bar need refreshing, and
            # only a couple times a second -- redrawing every frame would
            # just repaint the identical "0:03" position most frames.
            self._audio_status_elapsed += dt
            if self._audio_status_elapsed >= _AUDIO_STATUS_INTERVAL:
                self._audio_status_elapsed = 0.0
                self._refresh_audio_ui()
        elif self.mode == _MODE_RENAME and self.text_field is not None:
            self.text_field.tick()

    def onkeydown(self, keycode):
        if self._dialog is not None:
            if self._dialog.handle_key(keycode):
                self._dialog = None
            return
        if self.mode == _MODE_LIST:
            self._onkeydown_list(keycode)
        elif self.mode == _MODE_PREVIEW:
            self._onkeydown_preview(keycode)
        elif self.mode == _MODE_AUDIO:
            self._onkeydown_audio(keycode)
        elif self.mode == _MODE_RENAME:
            self._onkeydown_rename(keycode)

    def stop(self):
        if self.mode == _MODE_AUDIO:
            self.audio["stop_stream"]()
        print("[File Browser] Stopped")
