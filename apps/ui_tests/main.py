"""UI Test — a tabbed gallery exercising every widget in the ui/images/
animation/leds packages, for quickly checking a change looks right without
writing a one-off headless script each time.

LEFT/RIGHT switch tabs; ESC returns to the launcher. Each tab owns its own
keys beyond that (shown in the header hint) — text_field intentionally
doesn't bind LEFT/A or RIGHT/D as tab-switch aliases (unlike launcher/
app_settings) since it needs the full alphabet for typing.
"""

from __future__ import annotations

import os
import time

from core_os.apps_runtime.app_base import AppBase

_CONTENT_MARGIN = 4
_HEADER_GAP = 2


class _Swatch:
    """Fixed-size leaf widget that draws via an arbitrary callback instead
    of text -- used by the `rendering` tab to prove layout.Column(scroll=True)
    scrolls whatever's handed to it (draw_area/invert_area/overlay swatches
    here), not just wrapped text like ScrollPanel. Centers itself within
    whatever bounds it's actually given (which, via fill()/the cross-axis
    always getting the full inner width/height regardless of size tag --
    see layout._Stack.set_bounds's Pass 2 -- can be bigger than `size`),
    rather than always drawing flush at its own top-left corner."""

    def __init__(self, size: int, draw_fn) -> None:
        self._size = size
        self._draw_fn = draw_fn
        self.x = self.y = self.width = self.height = 0

    def measure(self, available_w: int, available_h: int):
        return (self._size, self._size)

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height

    def draw(self) -> None:
        ox = self.x + max(0, (self.width - self._size) // 2)
        oy = self.y + max(0, (self.height - self._size) // 2)
        self._draw_fn(ox, oy)

    def handle_key(self, keycode: str) -> bool:
        return False


_TABS = [
    "menu",
    "text_field",
    "toast",
    "dialog",
    "progress_bar",
    "scroll_panel",
    "text_box",
    "layout",
    "images",
    "animation",
    "tween",
    "rendering",
    "scroll_modes",
    "leds",
]

_HINTS = {
    "menu": "UP/DOWN  Enter",
    "text_field": "Type text, Enter submit",
    "toast": "1 Loading  2 Message  3 Error",
    "dialog": "Enter: open confirm",
    "progress_bar": "(auto-filling)",
    "scroll_panel": "UP/DOWN scroll",
    "text_box": "(static, max_lines=2)",
    "layout": "(static Row/Column)",
    "images": "(static draw_file + gif)",
    "animation": "Enter: replay slide+scale",
    "tween": "(auto: linear/in/out/in_out)",
    "rendering": "UP/DOWN scroll",
    "scroll_modes": "Enter: toggle snap/free  UP/DOWN scroll",
    "leds": "1 Solid  2 Blink  3 Chase  0 Off",
}

_LOREM = (
    "This ScrollPanel word-wraps a long block of text to the given width "
    "and lets you scroll it one line at a time with UP/DOWN, same as "
    "Menu's key bindings. The text is just a placeholder for testing, "
    "so it doesn't mean anything. The quick brown fox jumps over the lazy dog."
)


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.context = context
        self.gfx = context["display_gfx"]
        self.ui = context["ui"]
        self.images = context["images"]
        self.animation = context["animation"]
        self.leds = context["leds"]
        self.input = context["input"]
        self.app_control = context["app_control"]
        self.screen_width = context["screen_width"]
        self.screen_height = context["screen_height"]

        self.tab_index = 0
        self._last_update_time = None
        self._state = {}
        self._content_top = 0

    def start(self):
        print("[UI Test] Started")
        self._enter_tab()

    # --- tab plumbing ------------------------------------------------------

    def _tab_name(self):
        return _TABS[self.tab_index]

    def _render_header(self):
        small = self.gfx["fonts"]["small"]
        index_label = f"{self.tab_index + 1}/{len(_TABS)}"
        title = self.ui["label"](
            f"{index_label} {self._tab_name()}", font=small)
        hint = self.ui["label"](_HINTS[self._tab_name()], font=small)
        header = self.ui["column"](
            [self.ui["content"](title), self.ui["content"](hint)], spacing=2, margin=4)
        # Measure BEFORE laying out: a Column always renders its CONTENT
        # children at their own measured size regardless of the height
        # handed to layout_root (it doesn't shrink or clip them to fit), so
        # the header's real on-screen height can only be known by measuring
        # it directly -- assuming a fixed constant here is exactly what
        # silently drifted out of sync and let the header start colliding
        # with whatever tab content was hardcoded to start right below it.
        _, header_height = header.measure(
            self.screen_width, self.screen_height)
        self.ui["layout_root"](
            header, x=0, y=0, width=self.screen_width, height=header_height)
        self._content_top = header_height + _HEADER_GAP

    def _content_rect(self):
        """(x, y, width, height) of the space below the header, recomputed
        from the header's ACTUAL measured height every time a tab is
        (re)entered -- so tab content can never collide with the header
        regardless of how tall it ends up being."""
        x = _CONTENT_MARGIN
        y = self._content_top
        width = max(0, self.screen_width - 2 * _CONTENT_MARGIN)
        height = max(0, self.screen_height - y - _CONTENT_MARGIN)
        return x, y, width, height

    def _centered_origin(self, item_width, item_height):
        """Top-left (x, y) that centers an item_width x item_height block
        within the current content rect -- for the tab demos that don't
        need to fill the whole area (status text, the images/animation/
        progress_bar/layout demos), rather than pinning them to the
        content rect's top-left corner."""
        x, y, width, height = self._content_rect()
        return (
            x + max(0, (width - item_width) // 2),
            y + max(0, (height - item_height) // 2),
        )

    def _enter_tab(self):
        self._state = {}
        self.gfx["clear_screen"]()
        self._render_header()
        build_fn = getattr(self, f"_build_{self._tab_name()}", None)
        if build_fn:
            build_fn()

    def _switch_tab(self, direction):
        new_index = (self.tab_index + direction) % len(_TABS)
        self.tab_index = new_index
        self._enter_tab()

    # --- menu ---------------------------------------------------------------

    def _build_menu(self):
        x, y, width, height = self._content_rect()
        items = [self.ui["menu_item"](
            f"Item {i}", value=i) for i in range(1, 6)]
        menu = self.ui["menu"](items, x=x, y=y, width=width, height=height)
        menu.draw()
        self._state["menu"] = menu

    def _onkeydown_menu(self, keycode):
        self._state["menu"].handle_key(keycode)

    def _update_menu(self, dt):
        self._state["menu"].tick(dt)

    # --- text_field -----------------------------------------------------

    def _build_text_field(self):
        x, y, _, _ = self._content_rect()
        text_input = self.input["make_text_input"]()
        field = self.ui["text_field"](
            text_input, x=x, y=y, font=self.gfx["fonts"]["small"])
        field.draw()
        self._state["text_field"] = field

    def _onkeydown_text_field(self, keycode):
        self._state["text_field"].handle_key(keycode)

    def _update_text_field(self, dt):
        self._state["text_field"].tick()

    # --- toast --------------------------------------------------------------

    def _build_toast(self):
        self._state["toast"] = self.ui["toast"]()
        self._state["toast"].loading("Press 1/2/3")

    def _onkeydown_toast(self, keycode):
        toast = self._state["toast"]
        if keycode == "KEY_1":
            toast.loading("Loading something...")
        elif keycode == "KEY_2":
            toast.message(
                "Message", "Here's a message with a longer body to check wrapping.")
        elif keycode == "KEY_3":
            toast.error("Something went wrong")

    # --- dialog ---------------------------------------------------------

    def _build_dialog(self):
        self._state["dialog"] = None
        self._state["dialog_result"] = "(none yet)"
        self._draw_dialog_status()

    def _draw_dialog_status(self):
        x, y, width, height = self._content_rect()
        self.gfx["clear_area"](x, y, width, height)
        font = self.gfx["fonts"]["small"]
        text = f"Last choice: {self._state['dialog_result']}"
        text_w, text_h = self.gfx["get_text_size"](text, font)
        text_x, text_y = self._centered_origin(text_w, text_h)
        self.gfx["draw_text"](text, text_x, text_y, font=font)

    def _onkeydown_dialog(self, keycode):
        if self._state.get("dialog") is not None:
            self._state["dialog"].handle_key(keycode)
            return
        if keycode == "KEY_ENTER":
            def _on_yes():
                self._state["dialog"] = None
                self._state["dialog_result"] = "Yes"
                self._draw_dialog_status()

            def _on_no():
                self._state["dialog"] = None
                self._state["dialog_result"] = "No"
                self._draw_dialog_status()

            self._state["dialog"] = self.ui["dialog"](
                "Confirm", "Are you sure?", on_yes=_on_yes, on_no=_on_no)

    # --- progress_bar -----------------------------------------------------

    def _build_progress_bar(self):
        """Two bars demoing progress_bar's label/value props: the first
        auto-shows its live percentage (show_percent=True), the second
        shows an arbitrary value string (set_value_text) instead -- "n/10"
        rather than a percentage -- both with a label to their left."""
        x, y, width, _ = self._content_rect()
        font = self.gfx["fonts"]["small"]
        percent_bar = self.ui["progress_bar"](
            x=x, y=y, width=width, height=8, font=font, label="Loading", show_percent=True
        )
        count_bar = self.ui["progress_bar"](
            x=x, y=y + 14, width=width, height=8, font=font, label="Files"
        )
        percent_bar.set_progress(0.0)
        count_bar.set_progress(0.0)
        count_bar.set_value_text("0/10")
        self._state["progress_bars"] = (percent_bar, count_bar)
        self._state["progress_value"] = 0.0

    def _update_progress_bar(self, dt):
        percent_bar, count_bar = self._state["progress_bars"]
        value = (self._state["progress_value"] + dt / 2.0) % 1.0
        self._state["progress_value"] = value
        percent_bar.set_progress(value)
        count_bar.set_progress(value)
        count_bar.set_value_text(f"{int(value * 10)}/10")

    # --- scroll_panel -----------------------------------------------------

    def _build_scroll_panel(self):
        x, y, width, height = self._content_rect()
        panel = self.ui["scroll_panel"](
            x=x, y=y, width=width, height=height, text=_LOREM)
        panel.draw()
        self._state["scroll_panel"] = panel

    def _onkeydown_scroll_panel(self, keycode):
        self._state["scroll_panel"].handle_key(keycode)

    # --- text_box ---------------------------------------------------------

    def _build_text_box(self):
        _, _, content_width, content_height = self._content_rect()
        box = self.ui["text_box"](
            text=_LOREM, max_lines=2, padding=2, border=1,
        )
        box_width = content_width
        _, box_height = box.measure(box_width, content_height)
        x, y = self._centered_origin(box_width, box_height)
        box.set_bounds(x, y, box_width, box_height)
        box.draw()
        self._state["text_box"] = box

    # --- layout -------------------------------------------------------------

    def _layout_box(self, text, align):
        """A bordered box around a Label -- Label has no border/padding of
        its own (only Row/Column do), so it's wrapped in a Row for those.
        The label is tagged fill(), not content(): `align` only has
        anything to align WITHIN once the label's OWN bounds are wider
        than its text, and a content()-tagged child always gets exactly
        its own measured size regardless of how much room its parent
        actually has -- that holds at every nesting level, which is why
        the outer box itself also has to be fill()-tagged by the caller."""
        small = self.gfx["fonts"]["small"]
        label = self.ui["label"](text, font=small, align=align)
        return self.ui["row"]([self.ui["fill"](label)], border=1, padding=1)

    def _build_layout(self):
        _, _, content_width, content_height = self._content_rect()

        row1 = self.ui["row"](
            [self.ui["fill"](self._layout_box("Left", "center")), self.ui["fill"](
                self._layout_box("Right", "center"))],
            spacing=2,
        )
        row2 = self.ui["row"](
            [
                self.ui["fill"](self._layout_box("L", "center")),
                self.ui["fill"](self._layout_box("C", "center")),
                self.ui["fill"](self._layout_box("R", "center")),
            ],
            spacing=2,
        )
        stack = self.ui["column"](
            [self.ui["content"](row1), self.ui["content"](row2)], spacing=2)

        # Empty bordered spacer column, left of the row1/row2 stack, both
        # still inside the same outer box -- a Row with zero children still
        # draws its own border, no filler widget needed. Given a FIXED
        # pixel size (1/3 of root's own inner width, computed here rather
        # than left to fill()) instead of fill()/content(): fill() would
        # make it "whatever's left after stack", not a controlled fraction,
        # and stack's own content()-measured width doesn't reliably equal
        # 2/3 of anything either (see _layout_box's docstring on how little
        # content()'s natural size has to do with final on-screen width).
        outer_margin, outer_border, outer_padding, outer_spacing = 0, 0, 0, 2
        inner_width = max(0, content_width - 2 *
                          (outer_margin + outer_border + outer_padding))
        spacer_width = inner_width // 3
        spacer_box = self.ui["row"]([self.ui["fill"](self.ui["label"]("BOX", align="center"))], border=1, padding=2)

        content1 = self.ui["row"](
            [(spacer_box, spacer_width), self.ui["fill"](stack)],
            border=outer_border, padding=outer_padding, spacing=outer_spacing, margin=outer_margin
        )

        row3 = self.ui["row"](
            [self.ui["fill"](self._layout_box("This is a row!", "center"))]
        )

        root = self.ui["column"]([
            self.ui["content"](content1), self.ui["content"](row3)
        ], spacing=2, border=1, padding=2)

        _, root_height = root.measure(content_width, content_height)
        x, y = self._centered_origin(content_width, root_height)
        self.ui["layout_root"](
            root, x=x, y=y, width=content_width, height=root_height)

    # --- images -------------------------------------------------------------

    def _build_images(self):
        """Two cards side by side, each a column(label, image), built from
        row/column instead of hand-computed x/y like every other tab here --
        the label is a text_box (not label()) specifically because text_box
        word-wraps: the gif card's label is deliberately long enough to need
        it, rather than a single line that happened to fit.

        Both images go through ui["image"] (layout.Image) -- the promoted,
        first-class version of what used to be this tab's own private
        _Swatch/_FillImage leaf widgets: `size=32` centers a fixed-size
        static icon, `size="fill"` fills the whole box while preserving
        aspect ratio for the animated GIF, and GIF-vs-static is
        auto-detected from the path extension."""
        x, y, width, height = self._content_rect()
        font = self.gfx["fonts"]["small"]
        icon_path = os.path.join(os.path.dirname(__file__), "..", "proxi", "icon.png")
        gif_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "startup.gif")

        icon_label = self.ui["text_box"]("image:", font=font, max_lines=2)
        gif_label = self.ui["text_box"]("gif:", font=font, max_lines=2)

        icon_image = self.ui["image"](icon_path, size=32)
        gif_image = self.ui["image"](gif_path, size="fill", loop=True)
        self._state["images"] = [icon_image, gif_image]

        icon_box = self.ui["row"]([self.ui["fill"](icon_image)], border=1, padding=2)
        gif_box = self.ui["row"]([self.ui["fill"](gif_image)], border=1, padding=2)
        icon_card = self.ui["column"]([self.ui["content"](icon_label), self.ui["fill"](icon_box)], spacing=2)
        gif_card = self.ui["column"]([self.ui["content"](gif_label), self.ui["fill"](gif_box)], spacing=2)
        root = self.ui["row"]([self.ui["fill"](icon_card), self.ui["fill"](gif_card)], spacing=4)
        self.ui["layout_root"](root, x=x, y=y, width=width, height=height)

    def _update_images(self, dt):
        for image in self._state.get("images", []):
            image.update(dt)

    # --- animation ----------------------------------------------------------

    def _build_animation(self):
        self._state["anim_label"] = None
        self._state["scale_anim"] = None
        self._start_animation_demo()

    def _start_animation_demo(self):
        small = self.gfx["fonts"]["small"]
        text = "Sliding in!"
        text_w, text_h = self.gfx["get_text_size"](text, small)
        icon_size = 32
        gap = 6
        block_w = max(text_w, icon_size)
        block_h = text_h + gap + icon_size
        block_x, block_y = self._centered_origin(block_w, block_h)

        label = self.ui["label"](text, font=small)
        label.set_bounds(block_x, block_y, block_w, text_h)
        self._state["slide_anim"] = self.animation["doslide"](
            label, from_x=self.screen_width, duration=0.3)

        icon_path = os.path.join(os.path.dirname(
            __file__), "..", "proxi", "icon.png")
        if os.path.isfile(icon_path):
            icon_center_x = block_x + block_w // 2
            icon_center_y = block_y + text_h + gap + icon_size // 2
            self._state["scale_anim"] = self.animation["doscale"](
                icon_path, icon_center_x, icon_center_y, target_size=icon_size, duration=0.4
            )

    def _onkeydown_animation(self, keycode):
        if keycode == "KEY_ENTER":
            x, y, width, height = self._content_rect()
            self.gfx["clear_area"](x, y, width, height)
            self._start_animation_demo()

    def _update_animation(self, dt):
        slide_anim = self._state.get("slide_anim")
        if slide_anim is not None:
            slide_anim.update(dt)
            if slide_anim.done:
                self._state["slide_anim"] = None
        scale_anim = self._state.get("scale_anim")
        if scale_anim is not None:
            scale_anim.update(dt)
            if scale_anim.done:
                self._state["scale_anim"] = None

    # --- tween ------------------------------------------------------------

    # One row per easing curve animation.tween accepts by name (see
    # animation/easing.py's EASINGS) -- ping-ponging independently so all
    # four are visible side by side rather than replaying one at a time.
    _TWEEN_EASINGS = ("linear", "ease_in", "ease_out", "ease_in_out")

    def _build_tween(self):
        x, y, width, _ = self._content_rect()
        font = self.gfx["fonts"]["small"]
        box = 8
        label_w = 66
        row_h = max(box, self.gfx["line_height"]("Ag", font)) + 4
        track_x0 = x + label_w
        track_x1 = x + max(box, width - label_w) - box

        rows = []
        for i, name in enumerate(self._TWEEN_EASINGS):
            row_y = y + i * row_h
            self.gfx["draw_text"](name, x, row_y, font=font)
            rows.append({"name": name, "y": row_y, "dir": 1,
                        "last_rect": None, "tween": None})

        self._state["tween_rows"] = rows
        self._state["tween_track"] = (track_x0, track_x1)
        self._state["tween_box"] = box
        for row in rows:
            self._start_tween_row(row)

    def _start_tween_row(self, row):
        track_x0, track_x1 = self._state["tween_track"]
        from_x = track_x0 if row["last_rect"] is None else row["last_rect"][0]
        to_x = track_x1 if row["dir"] == 1 else track_x0
        row["tween"] = self.animation["tween"](
            from_x, to_x, duration=1.2, easing=row["name"])

    def _update_tween(self, dt):
        box = self._state["tween_box"]
        for row in self._state["tween_rows"]:
            tween = row["tween"]
            tween.update(dt)
            x = int(round(tween.value))
            y = row["y"]
            if row["last_rect"] is not None:
                self.gfx["clear_area"](*row["last_rect"])
            self.gfx["draw_area"](x, y, box, box)
            row["last_rect"] = (x, y, box, box)
            if tween.done:
                row["dir"] *= -1
                self._start_tween_row(row)

    # --- rendering ----------------------------------------------------------

    def _rendering_row(self, swatch_size, draw_fn, label_text):
        font = self.gfx["fonts"]["small"]
        swatch = _Swatch(swatch_size, draw_fn)
        label = self.ui["label"](label_text, font=font)
        return self.ui["row"]([self.ui["content"](swatch), self.ui["content"](label)], spacing=4)

    def _build_rendering(self):
        """One row per display_gfx primitive no other tab touches -- a
        filled rect (draw_area), a filled rect with an inverted sub-region
        (invert_area, same mechanism layout._Stack uses for its `inverted`
        boxes), and the overlay layer (draw_overlay_area). Scrolled via
        column(scroll=True) rather than a hand-rolled offset, proving the
        modular scroll works for arbitrary drawn content, not just text
        (see ScrollPanel, which is the text-only special case of the same
        primitive)."""
        x, y, width, height = self._content_rect()
        swatch = 20

        def draw_area_swatch(px, py):
            self.gfx["draw_area"](px, py, swatch, swatch)

        def invert_area_swatch(px, py):
            self.gfx["draw_area"](px, py, swatch, swatch)
            self.gfx["invert_area"](px + 5, py + 5, swatch - 10, swatch - 10)

        def overlay_swatch(px, py):
            self.gfx["draw_overlay_area"](px, py, swatch, swatch, fill=255)

        rows = [
            self.ui["content"](self._rendering_row(
                swatch, draw_area_swatch, "draw_area")),
            self.ui["content"](self._rendering_row(
                swatch, invert_area_swatch, "invert_area")),
            self.ui["content"](self._rendering_row(
                swatch, overlay_swatch, "overlay")),
        ]
        column = self.ui["column"](rows, spacing=4, scroll=True)

        self._state["rendering"] = column
        self._state["rendering_rect"] = (x, y, width, height)
        # The overlay swatch's ink lives on a layer separate from the base
        # one column.draw() clears -- without this, scrolling it out of
        # view would leave it ghosted behind whatever scrolls into its spot.
        self.gfx["clear_overlay_area"](x, y, width, height)
        column.set_bounds(x, y, width, height)
        column.draw()

    def _onkeydown_rendering(self, keycode):
        self.gfx["clear_overlay_area"](*self._state["rendering_rect"])
        self._state["rendering"].handle_key(keycode)

    # --- scroll_modes ---------------------------------------------------

    _SCROLL_MODES_LINE_COUNT = 10

    def _build_scroll_modes(self):
        self._state["scroll_modes_snap"] = True
        self._rebuild_scroll_modes()

    def _rebuild_scroll_modes(self):
        """Same content, same column(scroll=True), rebuilt with `scroll_snap`
        flipped by Enter -- side by side this would just be two scrollers,
        but toggling one in place makes the difference (whole-row jumps vs.
        pixel-stepped, partially-visible rows) obvious without needing to
        remember what the other one looked like."""
        x, y, width, height = self._content_rect()
        font = self.gfx["fonts"]["small"]
        snap = self._state["scroll_modes_snap"]

        mode_label = self.ui["label"](
            f"mode: {'snap' if snap else 'free'}", font=font)
        lines = [
            self.ui["content"](self.ui["label"](
                f"Line {i} of sample text", font=font))
            for i in range(self._SCROLL_MODES_LINE_COUNT)
        ]
        scroller = self.ui["column"](
            lines, spacing=1, scroll=True, scroll_snap=snap, scroll_step=4)
        root = self.ui["column"](
            [self.ui["content"](mode_label), self.ui["fill"](scroller)], spacing=2)
        root.set_bounds(x, y, width, height)
        root.draw()
        self._state["scroll_modes_root"] = root

    def _onkeydown_scroll_modes(self, keycode):
        if keycode == "KEY_ENTER":
            self._state["scroll_modes_snap"] = not self._state["scroll_modes_snap"]
            self._rebuild_scroll_modes()
            return
        self._state["scroll_modes_root"].handle_key(keycode)

    # --- leds -----------------------------------------------------------

    def _build_leds(self):
        self._state["leds_status"] = "off"
        self._draw_leds_status()

    def _draw_leds_status(self):
        x, y, width, height = self._content_rect()
        self.gfx["clear_area"](x, y, width, height)
        font = self.gfx["fonts"]["small"]
        text = f"leds: {self._state['leds_status']}"
        text_w, text_h = self.gfx["get_text_size"](text, font)
        text_x, text_y = self._centered_origin(text_w, text_h)
        self.gfx["draw_text"](text, text_x, text_y, font=font)

    def _onkeydown_leds(self, keycode):
        if keycode == "KEY_1":
            self.leds["set_solid"](255, 0, 0)
            self._state["leds_status"] = "solid red"
        elif keycode == "KEY_2":
            self.leds["blink"](0, 255, 0)
            self._state["leds_status"] = "blink green"
        elif keycode == "KEY_3":
            self.leds["chase"]([(0, 0, 255), (255, 255, 255)])
            self._state["leds_status"] = "chase blue/white"
        elif keycode == "KEY_0":
            self.leds["off"]()
            self._state["leds_status"] = "off"
        else:
            return
        self._draw_leds_status()

    # --- app lifecycle ------------------------------------------------------

    def update(self):
        now = time.monotonic()
        dt = 0.0 if self._last_update_time is None else now - self._last_update_time
        self._last_update_time = now
        update_fn = getattr(self, f"_update_{self._tab_name()}", None)
        if update_fn:
            update_fn(dt)

    def onkeydown(self, keycode):
        if keycode == "KEY_LEFT":
            self._switch_tab(-1)
            return
        if keycode == "KEY_RIGHT":
            self._switch_tab(1)
            return
        if keycode == "KEY_ESC":
            self.app_control.swap_app_async("ui_test", "launcher", delay=0.1)
            return
        onkeydown_fn = getattr(self, f"_onkeydown_{self._tab_name()}", None)
        if onkeydown_fn:
            onkeydown_fn(keycode)

    def stop(self):
        print("[UI Test] Stopped")
