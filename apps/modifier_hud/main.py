"""Modifier HUD — an always-running overlay (see bootstrap.run's
start_overlay call) that pops a small card up from the bottom edge of the
screen whenever ALT/CTRL/CMD/FN is held, and slides it back down once
every one of them is released. SHIFT is deliberately excluded from the
card -- it's already visible in what's being typed (letters go uppercase),
so a HUD for it would just be noise.

FN gets more than a label, though: it silently swaps the letter keys to
symbols, with no physical change to the keyboard to look at, so while FN
is held (alone or with other modifiers) this HUD instead slides up a
small card holding just those remapped keys (QWERTYUIOP/ASDFGHJKL/ZXCVBNM,
the ones fn_key_map/fn_shift_key_map actually touch), staggered left-to-
right the same way the real rows are, each re-labeled to whatever symbol
it currently produces -- see _Keyboard/_LAYOUT. Digits, space, enter, and
the modifier keys themselves don't change under FN, so they're left off
entirely rather than padding out the card. SHIFT is tracked separately
(_shift_held) purely to pick fn_key_map vs fn_shift_key_map for that
relabeling; it still never appears on the small ALT/CTRL/CMD/FN card.

_Card and _Keyboard are two interchangeable "slide-up panels" sharing one
interface (resting_y()/draw_at()/hide()) and one animation (_card_y/
_tween on App) -- only one is ever _active at a time, so pressing FN while
ALT is already up hides the ALT pill and slides the keyboard up in its
place instead of showing both.

Drawn entirely on the overlay compositing layer (draw_overlay_*/
clear_overlay_area) rather than DoSlide/the base layer -- dispatch_focused
delivers onkeydown/onkeyup to this app AND the focused app simultaneously
(see core/event_bus.py), so this HUD is always compositing on top of
whatever that app is drawing on the base layer; touching the base layer
here would fight with it instead. DoSlide itself clears the base layer
between frames (see animation/package.py's docstring), so it isn't reused
here either -- the card manages its own previous-frame clear on the
overlay layer instead (see _Card.draw_at).
"""

from __future__ import annotations

from core_os.apps_runtime.app_base import AppBase

# Every physical modifier keycode that can produce each label. FN1/FN2 (one
# at each end of the bottom row, same idea as left/right shift) both read
# as plain "FN" -- which physical FN key it was doesn't matter for display.
_MODIFIER_LABELS = {
    "KEY_FN1": "FN",
    "KEY_FN2": "FN",
    "KEY_LEFTALT": "ALT",
    "KEY_RIGHTALT": "ALT",
    "KEY_LEFTCTRL": "CTRL",
    "KEY_RIGHTCTRL": "CTRL",
    "KEY_CMD": "CMD",
}

_SLIDE_DURATION = 0.2
_BOTTOM_MARGIN = 2
_PADDING = 4
_SIDE_MARGIN = 6
_CORNER_RADIUS = 3

# Only the letter keys fn_key_map/fn_shift_key_map actually remap (see
# input.apply_modifier_mapping -- non-letter keycodes pass FN straight
# through untouched). BACKSPACE/COLON/COMMA/ENTER share these physical rows
# (see core_os/backends/device_pi/input.py's KEYMAP) but FN doesn't change
# what they produce -- kept in the layout at their real position (rather
# than left off, which used to make rows a spreadsheet-y mismatched
# length) but drawn dithered instead of plain white, so the card still
# reads as "FN remaps this" only for the cells that actually do.
_LAYOUT = [
    ["KEY_TAB", "KEY_Q", "KEY_W", "KEY_E", "KEY_R", "KEY_T", "KEY_Y", "KEY_U", "KEY_I", "KEY_O", "KEY_P", "KEY_BACKSPACE"],
    ["KEY_LEFTSHIFT", "KEY_A", "KEY_S", "KEY_D", "KEY_F", "KEY_G", "KEY_H", "KEY_J", "KEY_K", "KEY_L", "KEY_ENTER"],
    ["KEY_FN1", "KEY_Z", "KEY_X", "KEY_C", "KEY_SPACE", "KEY_V", "KEY_B", "KEY_N", "KEY_M", "KEY_HOME"],
]

# These never change under FN -- drawn as a dithered (not plain white),
# unlabeled cell, distinguishing "present but unaffected" from the live-
# remapped letter keys around them at a glance. FN itself is included too
# (it's the reason the card is up at all, but it doesn't change ITS own
# output any more than Tab/Bksp/etc do). KEY_HOME has no real handling
# anywhere yet (see the emulator device map's own invented Home key); it's
# only ever a blank placeholder here too.
_SPECIAL_KEYS = {"KEY_TAB", "KEY_BACKSPACE", "KEY_LEFTSHIFT", "KEY_ENTER", "KEY_SPACE", "KEY_HOME", "KEY_FN1"}

# Width, as a multiple of one normal key's width -- matches the physical
# key sizes the emulator's device control map uses for these same keys
# (core_os/backends/emulator_windows/emulator_display.py's
# _layout_alpha_rows), so the card reads as the actual keyboard shape
# rather than a uniform grid. Anything not listed (letters, Tab, Bksp,
# Home) is a normal 1x key.
_KEY_WIDTH_MULT = {
    "KEY_SPACE": 2.0,
    "KEY_FN1": 2.0,
    "KEY_LEFTSHIFT": 1.5,
    "KEY_ENTER": 1.5,
}

_KB_PADDING = 2
_KB_GAP = 0  # cells touch edge-to-edge; the 1px grid line at each boundary
# is the only visual separator -- a real gap left a sliver of the card's
# plain white background between cells that a dithered cell's own fill
# didn't reach, breaking its pattern right at the edge.

# Per-row horizontal stagger, as a fraction of one normal key's width --
# real keyboard rows aren't stacked in a strict grid, each one sits offset
# from the row above (home row shifted right of the top row, bottom row
# shifted further still), so a plain grid would read as a spreadsheet
# rather than a keyboard. Fractions approximate a standard keyboard's
# stagger; exact alignment with the physical device doesn't matter here
# since this is a legend, not a hit-testable layout.
_ROW_STAGGER = [0.0, 0.25, 0.5]


class _Keyboard:
    """Small cheat-sheet card for the FN-remapped keys, sliding up from the
    bottom edge the same way _Card does -- see App's shared _card_y/_tween
    animation and resting_y()/draw_at()/hide() (the interface both panels
    share). Rows are staggered per _ROW_STAGGER so the card reads as a
    (rough) keyboard shape rather than a strict grid; key widths follow
    _KEY_WIDTH_MULT so Space/Shft/Ent are the same relative size as the
    real keys instead of a uniform column grid."""

    def __init__(self, gfx, screen_width: int, screen_height: int, layout) -> None:
        self._gfx = gfx
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._font = gfx["fonts"]["small"]
        self._layout = layout
        self._labels: list = [[] for _ in layout]
        self._last_rect = None

        # One normal key's width, solved so row 0 (Tab...Bksp, all 1x keys)
        # exactly fills the available width -- every other row's cells and
        # stagger offset are sized off this same unit, matching the device
        # map's "row 0 is the reference" approach.
        reference_row = layout[0]
        reference_units = sum(_KEY_WIDTH_MULT.get(kc, 1.0) for kc in reference_row)
        available_w = screen_width - _SIDE_MARGIN * 2
        self._key_size = (available_w - (len(reference_row) - 1) * _KB_GAP) / reference_units

    def set_labels(self, labels) -> None:
        self._labels = labels

    def _row_geometry(self, row_idx: int):
        """[(rel_x, width, keycode), ...] for this row, plus its own total
        content width (last entry's rel_x + width)."""
        x = 0.0
        entries = []
        for keycode in self._layout[row_idx]:
            width = round(self._key_size * _KEY_WIDTH_MULT.get(keycode, 1.0))
            entries.append((round(x), width, keycode))
            x += width + _KB_GAP
        content_w = (entries[-1][0] + entries[-1][1]) if entries else 0
        return entries, content_w

    def _dimensions(self):
        _, text_h = self._gfx["get_text_size"]("Ag", self._font)
        row_h = text_h + _KB_PADDING * 2
        box_w = 0
        for row_idx in range(len(self._layout)):
            _, content_w = self._row_geometry(row_idx)
            stagger_px = round(_ROW_STAGGER[row_idx] * self._key_size)
            box_w = max(box_w, stagger_px + content_w)
        box_h = len(self._layout) * row_h
        return row_h, box_w, box_h

    def resting_y(self) -> int:
        # Flush with the bottom edge, unlike _Card's pill (_BOTTOM_MARGIN) --
        # only the top corners are rounded (see draw_at), so docking it
        # right against the edge reads as "anchored to the edge" rather
        # than floating just above it.
        _, _, box_h = self._dimensions()
        return self.screen_height - box_h

    def draw_at(self, y: float) -> None:
        if y >= self.screen_height:
            self.hide()
            return
        gfx = self._gfx
        row_h, box_w, box_h = self._dimensions()
        x0 = (self.screen_width - box_w) // 2
        y_i = int(round(y))
        rect = (x0, y_i, box_w, box_h)
        if self._last_rect is not None and self._last_rect != rect:
            gfx["clear_overlay_area"](*self._last_rect)
        gfx["draw_overlay_area"](
            x0, y_i, box_w, box_h, fill=255, radius=_CORNER_RADIUS, corners=(True, True, False, False),
        )
        for r, row_cells in enumerate(self._labels):
            ry = y_i + r * row_h
            row_geometry = self._row_geometry(r)[0]
            row_x0 = x0 + round(_ROW_STAGGER[r] * self._key_size)
            # Dithered cell backgrounds first -- the grid-line separators
            # below are drawn on top of them, not the other way round, so a
            # dithered cell doesn't paint over (and erase) the row/column
            # line right next to it.
            last_c = len(row_geometry) - 1
            for c, ((rel_x, width, keycode), (label, dithered)) in enumerate(zip(row_geometry, row_cells)):
                if dithered:
                    # "Present but FN doesn't change it" -- a light stipple
                    # instead of the plain white the live-remapped letter
                    # cells get, and left unlabeled, so the two read as
                    # visually distinct at a glance rather than needing the
                    # label read closely.
                    #
                    # Row 0 is the only row touching the card's rounded top
                    # edge (see draw_overlay_area above) -- its first/last
                    # cell need the SAME corner rounding applied to their
                    # dither fill, or that fill (a plain rect) paints right
                    # back over the rounded corner and squares it off again.
                    radius, corners = 0, None
                    if r == 0 and c == 0:
                        radius, corners = _CORNER_RADIUS, (True, False, False, False)
                    elif r == 0 and c == last_c:
                        radius, corners = _CORNER_RADIUS, (False, True, False, False)
                    gfx["draw_overlay_area_pattern"](
                        row_x0 + rel_x, ry, width, row_h, gfx["patterns"]["gray-25"], fill=0, bg=255,
                        radius=radius, corners=corners,
                    )
            if r > 0:
                gfx["draw_overlay_area"](x0, ry, box_w, 1, fill=0)
            for c, ((rel_x, width, keycode), (label, dithered)) in enumerate(zip(row_geometry, row_cells)):
                cx = row_x0 + rel_x
                if c > 0:
                    gfx["draw_overlay_area"](cx, ry, 1, row_h, fill=0)
                if dithered or not label:
                    continue
                text_w, th = gfx["get_text_size"](label, self._font)
                tx = cx + max((width - text_w) // 2, 0)
                ty = ry + max((row_h - th) // 2, 0)
                gfx["draw_overlay_text"](label, tx, ty, font=self._font, fill=0)
        self._last_rect = rect

    def hide(self) -> None:
        if self._last_rect is not None:
            self._gfx["clear_overlay_area"](*self._last_rect)
            self._last_rect = None

    @property
    def visible(self) -> bool:
        return self._last_rect is not None


class _Card:
    """A compact, auto-width label box anchored to the bottom edge. `y` is
    the animated top-left y of the box; draw_at()/hide() are the only two
    ways it ever touches the overlay layer, and both always clear whatever
    rect they last drew (even across a text change that resizes the box) so
    no frame ever leaves stale ink from a previous size/position behind."""

    def __init__(self, gfx, screen_width: int, screen_height: int) -> None:
        self._gfx = gfx
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._font = gfx["fonts"]["small"]
        self.text = ""
        self._last_rect = None

    def set_text(self, text: str) -> None:
        self.text = text

    @property
    def height(self) -> int:
        _, text_h = self._gfx["get_text_size"](self.text or " ", self._font)
        return text_h + _PADDING * 2

    def resting_y(self) -> int:
        return self.screen_height - self.height - _BOTTOM_MARGIN

    def draw_at(self, y: float) -> None:
        if not self.text or y >= self.screen_height:
            self.hide()
            return
        text_w, text_h = self._gfx["get_text_size"](self.text, self._font)
        width = text_w + _PADDING * 2
        height = text_h + _PADDING * 2
        x = (self.screen_width - width) // 2
        y_i = int(round(y))
        rect = (x, y_i, width, height)
        if self._last_rect is not None and self._last_rect != rect:
            self._gfx["clear_overlay_area"](*self._last_rect)
        self._gfx["draw_overlay_area"](x, y_i, width, height, fill=255)
        self._gfx["draw_overlay_text"](self.text, x + _PADDING, y_i + _PADDING, font=self._font, fill=0)
        self._last_rect = rect

    def hide(self) -> None:
        if self._last_rect is not None:
            self._gfx["clear_overlay_area"](*self._last_rect)
            self._last_rect = None


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.gfx = context["display_gfx"]
        self.animation = context["animation"]
        self.input = context["input"]
        self.timers = context["timer"]["timer_manager"]()
        self.screen_width = context["screen_width"]
        self.screen_height = context["screen_height"]
        self._held: dict = {}  # insertion-ordered set (dict, no values used) -- so "FN + ALT" stays in the
        # order the keys were actually pressed instead of whatever order set() iteration happens to give
        self._shift_held = False
        self._card = None
        self._keyboard = None
        self._active = None
        self._card_y = 0.0
        self._tween = None

    def start(self):
        self._card = _Card(self.gfx, self.screen_width, self.screen_height)
        self._keyboard = _Keyboard(self.gfx, self.screen_width, self.screen_height, _LAYOUT)
        self._active = self._card
        self._card_y = float(self.screen_height)

    def _labels(self):
        seen = []
        for keycode in self._held:
            label = _MODIFIER_LABELS.get(keycode)
            if label and label not in seen:
                seen.append(label)
        return seen

    def _fn_held(self) -> bool:
        return "KEY_FN1" in self._held or "KEY_FN2" in self._held

    def _key_label(self, keycode: str) -> str:
        mapped = self.input["apply_modifier_mapping"](keycode, self._shift_held, True)
        return self.input["key_map"].get(mapped, "")

    def _keyboard_labels(self):
        return [
            [
                ("", True) if kc in _SPECIAL_KEYS else (self._key_label(kc), False)
                for kc in row
            ]
            for row in _LAYOUT
        ]

    def _slide_to(self, target_y: float):
        self._tween = self.animation["tween"](self._card_y, target_y, duration=_SLIDE_DURATION, easing="ease_out")

    def _hidden(self) -> bool:
        return self._tween is None and self._card_y >= self.screen_height

    def _sync(self):
        """Single source of truth for what should be showing -- FN held
        means the keyboard card, otherwise the ALT/CTRL/CMD pill (if any
        of those are held). Both panels share one slide animation
        (_card_y/_tween), so switching between them just hides whichever
        one isn't relevant and slides the other up fresh; re-syncing the
        SAME panel while it's already up (e.g. SHIFT toggling while FN is
        still held, or a second modifier joining the pill) just refreshes
        its content in place without restarting the animation."""
        if self._fn_held():
            panel, want_visible = self._keyboard, True
        else:
            panel, want_visible = self._card, bool(self._labels())

        if not want_visible:
            if not self._hidden():
                self._slide_to(float(self.screen_height))
            return

        entering = self._active is not panel or self._hidden()
        if self._active is not panel:
            self._active.hide()
            self._active = panel
        if panel is self._card:
            self._card.set_text(" + ".join(self._labels()))
        else:
            self._keyboard.set_labels(self._keyboard_labels())
        if entering:
            self._card_y = float(self.screen_height)
            self._slide_to(panel.resting_y())
        elif self._tween is None:
            panel.draw_at(self._card_y)

    def onkeydown(self, keycode):
        if keycode == "KEY_LEFTSHIFT":
            self._shift_held = True
            self._sync()
            return
        if keycode not in _MODIFIER_LABELS or keycode in self._held:
            return
        self._held[keycode] = True
        self._sync()

    def onkeyup(self, keycode):
        if keycode == "KEY_LEFTSHIFT":
            self._shift_held = False
            self._sync()
            return
        if keycode not in _MODIFIER_LABELS or keycode not in self._held:
            return
        del self._held[keycode]
        self._sync()

    def update(self):
        dt = self.timers.tick()
        if self._tween is None:
            return
        self._tween.update(dt)
        self._card_y = self._tween.value
        self._active.draw_at(self._card_y)
        if self._tween.done:
            self._tween = None

    def stop(self):
        if self._card is not None:
            self._card.hide()
        if self._keyboard is not None:
            self._keyboard.hide()
