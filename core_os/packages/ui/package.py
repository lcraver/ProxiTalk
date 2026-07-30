"""ui package — reusable, easy-to-use common UI widgets for a 128x64 1-bit
display: Menu (list + selection + scrolling), TextField (wraps
utils/text_input.TextInput), Dialog, Toast, ProgressBar, ScrollPanel, Screen
— plus layout.py's Row/Column/Label for composing them without hardcoded
pixel positions.

Widgets are plain objects apps instantiate and drive explicitly: an app's own
onkeydown forwards to widget.handle_key(keycode), and drawing happens
automatically as part of handling input (or via an explicit .draw()). This
mirrors Tildagon's app_components (Menu/YesNoDialog/Notification — plain
method-driven objects, not separately scheduled entities): no scheduler or
event-bus involvement is needed here, only the App itself is registered for
event dispatch.

Every widget that has spacing/line-height baked into its rendering
(Menu/TextField/ScrollPanel) measures it fresh from the CURRENT font each
time — via display_gfx.get_text_size — instead of a fixed pixel constant.
misaki_gothic.ttf's kana glyphs measure a pixel taller than Latin ones
(see display_gfx.Package.line_height's docstring); without a fresh
measurement, a row-height baked in from Latin text would clip the bottom
row of any Japanese content.

Depends on display_gfx (package_requires) for all actual drawing.
"""

from __future__ import annotations

import math
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from core_os.packages.base import Package, PackageResources
from core_os.packages.ui.layout import CONTENT, FILL, Box, Column, Image, Label, Row


def _fill(node: Any) -> Tuple[Any, str]:
    """Tag `node` as a FILL child for a Row/Column's `children` list —
    context["ui"]["fill"](widget) instead of the caller writing
    (widget, context["ui"]["content"]/["fill"]) tuples by hand every time."""
    return (node, FILL)


def _content(node: Any) -> Tuple[Any, str]:
    """Tag `node` as a CONTENT child for a Row/Column's `children` list —
    see _fill's docstring."""
    return (node, CONTENT)


class MenuItem:
    def __init__(
        self, label: str, value: Any = None, toggled: Optional[bool] = None, icon: Optional[Any] = None
    ) -> None:
        self.label = label
        self.value = value if value is not None else label
        self.toggled = toggled
        # A pre-loaded, display-ready (mode '1') PIL Image, or None for no
        # icon -- Menu blits this via gfx.draw_image rather than accepting a
        # path, so a scrolling list with hundreds of rows never re-decodes
        # the same icon file per row per frame (see file_browser, which
        # loads each of its 5 category icons once and reuses the same
        # Image object across every row that needs it).
        self.icon = icon

    @property
    def display_label(self) -> str:
        if self.toggled is None:
            return self.label
        return f"[{'x' if self.toggled else ' '}] {self.label}"


class Menu:
    """A selectable, auto-scrolling list of MenuItems.

    row_height is measured fresh from the current font every time it's
    used (not a fixed constant), so it stays correct for whatever text is
    actually showing (e.g. misaki_gothic.ttf's kana glyphs measure a
    pixel taller than Latin ones) instead of causing overlapping rows.

    padding/margin/border/inverted follow the same CSS box model as
    layout._Stack and ui.TextBox (see their docstrings): margin moves
    self.bounds (and self.x/y/width/height, what a parent sees) in from
    whatever space was assigned; border draws at that (margined) edge and
    also insets where row content starts, same as a real border occupying
    space rather than overlapping content; padding then further insets
    row content from there (on all four sides — previously this was a
    hardcoded `x + 2` for the row text's left edge only, baked directly
    into draw() instead of being a real, symmetric, overridable inset);
    inverted pixel-inverts the whole menu after drawing, same as
    layout._Stack's — note this also flips the MEANING of the selected
    row's own highlight, since that's drawn as its own black-on-white
    inversion first and then gets inverted again along with everything
    else, the same "invert whatever was actually drawn" contract as
    always, just visibly interacting with a widget that already inverts
    part of itself.

    Each row's text is vertically centered within row_height using that
    row's OWN glyph height (not the row_height reference, which could be
    taller if some other item in the list needs more room) — previously
    rows were drawn flush at the row's top edge with no centering, which
    looked visibly off whenever an item's own text was shorter than
    row_height's shared reference.

    The selection highlight glides between rows over _HIGHLIGHT_DURATION
    (via tween_factory, i.e. animation.tween) rather than snapping straight
    to the new row, UNLESS the move also scrolls the list (the whole window
    of visible rows shifts at once, which isn't worth animating) or no
    tween_factory was supplied. Like TextField's cursor-blink tick(), this
    only advances if the owning app calls .tick(dt) once per frame from its
    own update() -- handle_key() alone only starts the animation, it
    doesn't run it."""

    _HIGHLIGHT_DURATION = 0.12

    # "Can't move further" feedback when UP/DOWN is pressed at either end
    # of the list: the halo's height briefly shrinks and returns (see
    # _start_shake/_shake_progress/draw), anchored at the edge actually
    # against the boundary -- top-anchored (shrinks from the bottom) for
    # KEY_UP at row 0, bottom-anchored (shrinks from the top) for KEY_DOWN
    # at the last row -- rather than a generic side-to-side wiggle.
    # Independent of and not requiring tween_factory -- this is a fixed
    # half-sine computed directly from elapsed time, not something a
    # Tween's single from->to interpolation can express.
    _SHAKE_DURATION = 0.2
    _SHAKE_AMPLITUDE = 3

    def __init__(
        self,
        gfx,
        items: List[Any],
        x: int = 0,
        y: int = 0,
        width: int = 128,
        height: int = 64,
        on_select: Optional[Callable[[MenuItem], None]] = None,
        on_change: Optional[Callable[[Optional[MenuItem]], None]] = None,
        row_height: Optional[int] = None,
        padding: int = 2,
        margin: int = 0,
        border: int = 0,
        inverted: bool = False,
        selected_padding: Optional[int] = None,
        spacing: int = 0,
        highlight_easing: str = "ease_out",
        highlight_settle_easing: Optional[str] = None,
        highlight_duration: Optional[float] = None,
        tween_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._gfx = gfx
        self.padding = padding
        self.margin = margin
        self.border = border
        self.spacing = spacing
        self._highlight_easing = highlight_easing
        self._highlight_settle_easing = highlight_settle_easing
        self._highlight_duration = self._HIGHLIGHT_DURATION if highlight_duration is None else highlight_duration
        self.inverted = inverted
        self.selected_padding = self.SELECTED_HALO_PADDING if selected_padding is None else selected_padding
        self.x, self.y, self.width, self.height = x, y, width, height
        self.bounds = Box(x, y, width, height)
        self._row_height_override = row_height
        self.on_select = on_select
        self.on_change = on_change
        self._tween_factory = tween_factory
        self._highlight_tween = None
        self._scroll_tween = None
        self.selected_index = 0
        self._scroll_position = 0.0
        self._visual_row = 0.0
        self._shake_elapsed = 0.0
        self._shake_active = False
        self._shake_direction = 0
        self._row_height_cache: Optional[int] = None
        self._row_height_cache_key = None
        self._text_size_cache: Dict[Tuple[int, str], Tuple[int, int]] = {}
        self._ink_bbox_cache: Dict[Tuple[int, str], Tuple[int, int, int, int]] = {}
        self._visible_rows_cache = None
        self._visible_rows_cache_key = None
        self._layout_cache = None
        self._layout_cache_key = None
        self._last_draw_state = None
        # NOT self.set_items(items) -- that also draw()s, which at
        # construction time would run against whatever x/y/width/height
        # defaults were passed in (often unset/full-display placeholders;
        # see make_menu's docstring, "unpositioned at construction, sized
        # by a Column layout"), not the real position a parent layout
        # assigns via set_bounds() moments later. With margin/border now
        # in the picture those two rects can genuinely differ, and since
        # draw() only clear_area()s its OWN bounds, that first errant draw
        # left stale border/content pixels outside the real, later
        # (smaller/offset) draw's clear region -- verified: a bordered,
        # margined Menu showed a leftover full-width border framing the
        # whole display alongside its real, correctly-positioned one.
        self._set_items(items)

    # Gap between an item's icon and its label -- only reserved at all when
    # at least one item in the list actually has an icon (see _set_items),
    # so a plain text Menu (every other current caller) draws exactly as
    # before this existed.
    _ICON_GAP = 2

    def _set_items(self, items: List[Any]) -> None:
        self.items = [item if isinstance(item, MenuItem) else MenuItem(str(item)) for item in items]
        self.selected_index = min(self.selected_index, max(0, len(self.items) - 1))
        icon_widths = [item.icon.width for item in self.items if item.icon is not None]
        icon_heights = [item.icon.height for item in self.items if item.icon is not None]
        self._icon_col_width = (max(icon_widths) + self._ICON_GAP) if icon_widths else 0
        self._icon_max_height = max(icon_heights) if icon_heights else 0
        self._scroll_position = 0.0
        self._visual_row = float(self.selected_index)
        self._highlight_tween = None
        self._scroll_tween = None
        self._highlight_from_index = self.selected_index
        self._highlight_to_index = self.selected_index
        self._row_height_cache = None
        self._row_height_cache_key = None
        self._text_size_cache.clear()
        self._ink_bbox_cache.clear()
        self._visible_rows_cache = None
        self._visible_rows_cache_key = None
        self._layout_cache = None
        self._layout_cache_key = None
        self._last_draw_state = None

    def _items_signature(self) -> Tuple[Tuple[str, Optional[bool]], ...]:
        return tuple((item.label, item.toggled) for item in self.items)

    def _row_height_cache_signature(self):
        font = self._gfx.fonts["small"]
        return (id(font), self._row_height_override, self._items_signature())

    def _measure_text_size(self, text: str, font) -> Tuple[int, int]:
        key = (id(font), text)
        cached = self._text_size_cache.get(key)
        if cached is None:
            cached = self._gfx.get_text_size(text, font)
            self._text_size_cache[key] = cached
        return cached

    def _measure_ink_bbox(self, text: str, font) -> Tuple[int, int, int, int]:
        key = (id(font), text)
        cached = self._ink_bbox_cache.get(key)
        if cached is None:
            cached = self._gfx.ink_bbox(text, font)
            self._ink_bbox_cache[key] = cached
        return cached

    @property
    def row_height(self) -> int:
        if self._row_height_override is not None:
            return self._row_height_override
        cache_key = self._row_height_cache_signature()
        if self._row_height_cache is not None and self._row_height_cache_key == cache_key:
            return self._row_height_cache
        # All rows share one uniform height, so the reference has to
        # represent whatever's actually in the list right now (e.g. all-
        # Japanese item labels), not a fixed "Ag" — see
        # display_gfx.line_height's docstring. Joining every current
        # label into one reference string picks up the tallest glyph any
        # of them actually needs, same as a single-string widget would,
        # without requiring a per-row height (which would break the
        # uniform `row * row_height` position math this widget relies on).
        #
        # ink_bbox, not get_text_size/line_height, for the height itself:
        # get_text_size's metric bbox overshoots the real rendered ink by
        # a pixel for misaki_gothic.ttf's kana (verified: "設定" measures
        # 8px by metric but only paints 7px of real ink — same overshoot
        # measure_ink's docstring documents for width), while plain Latin
        # rows show no such overshoot. Basing row_height AND each row's own
        # centering (below, in draw()) on metric height mixed the two: an
        # all-Latin row centered with a symmetric 1px gap top/bottom, but
        # a Japanese-containing row centered as if it were 1px taller than
        # it really is, landing flush at the row's top edge instead.
        reference = " ".join(item.display_label for item in self.items)
        ink_h = self._measure_ink_bbox(reference, self._gfx.fonts["small"])[3]
        # Icons set the row height outright when any item has one -- text
        # just centers within whatever that gives it (see "centering"
        # below) -- rather than the text's own ink height fighting the
        # icon for control of the row, which left rows sized off the
        # (usually smaller) text with icons visually cramped/clipped.
        content_h = self._icon_max_height if self._icon_max_height else ink_h
        self._row_height_cache = content_h + 2
        self._row_height_cache_key = cache_key
        return self._row_height_cache

    @property
    def row_pitch(self) -> int:
        """Vertical distance from one row's top edge to the next -- just
        row_height when spacing=0, otherwise row_height plus a gap between
        rows (not added after the last one, same n-1-gaps convention
        Row/Column's `spacing` uses). Every place that positions rows by
        multiplying an index (row_y, highlight_y, scroll math, measure())
        uses this instead of row_height directly; row_height alone still
        drives each row's OWN centering/halo sizing, which shouldn't grow
        just because the gap between rows did."""
        return self.row_height + self.spacing

    def _make_layout_cache_key(self) -> Tuple[Any, ...]:
        font = self._gfx.fonts["small"]
        return (
            id(font),
            self.x,
            self.y,
            self.width,
            self.height,
            self.padding,
            self.margin,
            self.border,
            self.spacing,
            self.selected_padding,
            self.inverted,
            self.row_height,
            self.row_pitch,
            self._icon_col_width,
            self._items_signature(),
        )

    def _ensure_layout_cache(self) -> Dict[str, Any]:
        cache_key = self._make_layout_cache_key()
        if self._layout_cache is not None and self._layout_cache_key == cache_key:
            return self._layout_cache

        ix, iy, iw, ih = self._content_rect()
        # Text starts past the (list-wide, uniform) icon column, if any --
        # reserved from the WHOLE content width even for rows without their
        # own icon, so every row's label still lines up in one column
        # rather than icon-having rows alone getting pushed over.
        text_ix = ix + self._icon_col_width
        text_iw = max(0, iw - self._icon_col_width)
        font = self._gfx.fonts["small"]
        row_height = self.row_height
        row_pitch = self.row_pitch
        rows = []
        for idx, item in enumerate(self.items):
            label = self._clip_label(item.display_label, text_iw, font)
            ink_left, _, ink_w, ink_h = self._measure_ink_bbox(label, font)
            # The selection halo's HEIGHT tracks the icon (when any item has
            # one), not this row's own text ink -- otherwise a short label
            # like "../" gets a halo visibly shorter than the icon sitting
            # right next to it, while a long label's halo happens to look
            # closer to full height, an inconsistency that has nothing to
            # do with which row is actually selected. Width still hugs the
            # real text ink either way -- only height is normalized.
            halo_h = self._icon_max_height if self._icon_max_height else ink_h
            rows.append(
                {
                    "offset": idx * row_pitch,
                    "label": label,
                    "ink_left": ink_left,
                    "ink_w": ink_w,
                    "ink_h": ink_h,
                    "centering": max(0, (row_height - ink_h) // 2 - 1),
                    "halo_h": halo_h,
                    "halo_centering": max(0, (row_height - halo_h) // 2 - 1),
                    "icon": item.icon,
                }
            )

        layout = {
            "font": font,
            "ix": ix,
            "iy": iy,
            "iw": iw,
            "ih": ih,
            "text_ix": text_ix,
            "row_height": row_height,
            "row_pitch": row_pitch,
            "visible_rows": max(1, ih // row_pitch),
            "rows": rows,
        }
        self._layout_cache = layout
        self._layout_cache_key = cache_key
        self._visible_rows_cache = layout["visible_rows"]
        self._visible_rows_cache_key = (ih, row_pitch)
        return layout

    def _current_highlight_rect(self, layout: Dict[str, Any]) -> Optional[Tuple[int, int, int, int]]:
        if not self.items:
            return None
        scroll = self._scroll_position
        visible = layout["visible_rows"]
        row_in_window = self._visual_row - scroll
        if not (-1 <= row_in_window <= visible + 1):
            return None

        from_idx, to_idx = self._highlight_from_index, self._highlight_to_index
        frac = 1.0 if from_idx == to_idx else (
            max(0.0, min(1.0, (self._visual_row - from_idx) / (to_idx - from_idx)))
        )
        row_from = layout["rows"][from_idx]
        row_to = layout["rows"][to_idx]
        ink_left_a = row_from["ink_left"]
        ink_w_a = row_from["ink_w"]
        ink_left_b = row_to["ink_left"]
        ink_w_b = row_to["ink_w"]
        ink_left = ink_left_a + (ink_left_b - ink_left_a) * frac
        ink_w = ink_w_a + (ink_w_b - ink_w_a) * frac
        # halo_h/halo_centering, not ink_h/centering -- the halo's HEIGHT
        # tracks the icon column when there is one (see _ensure_layout_cache),
        # not each row's own text ink height, so it doesn't shrink for a
        # short label like "../" while looking closer to full height for a
        # long one.
        halo_h_a = row_from["halo_h"]
        halo_h_b = row_to["halo_h"]
        halo_h = halo_h_a + (halo_h_b - halo_h_a) * frac
        centering_a = row_from["halo_centering"]
        centering_b = row_to["halo_centering"]
        centering = centering_a + (centering_b - centering_a) * frac
        p = self.selected_padding
        # Vertical padding only applies to a text-sized halo (which needs
        # the breathing room around bare ink) -- an icon-sized halo is
        # already sized to something with real visual weight of its own,
        # so adding the same padding on top just makes the box visibly
        # taller than the icon it's supposed to match.
        vpad = 0 if self._icon_max_height else p
        highlight_y = layout["iy"] + (self._visual_row - scroll) * layout["row_pitch"] + centering
        hx = int(round(layout["text_ix"] + ink_left - p))
        hw = int(round(ink_w + 2 * p))
        hy_rest = highlight_y - vpad
        hh_rest = halo_h + 2 * vpad
        shrink = self._SHAKE_AMPLITUDE * self._shake_progress()
        if self._shake_active and self._shake_direction < 0:
            hy, hh = hy_rest, max(0.0, hh_rest - shrink)
        elif self._shake_active and self._shake_direction > 0:
            hh = max(0.0, hh_rest - shrink)
            hy = hy_rest + hh_rest - hh
        else:
            hy, hh = hy_rest, hh_rest
        top_bound, bottom_bound = layout["iy"] - p, layout["iy"] + layout["ih"] + p
        cy0 = max(top_bound, hy)
        cy1 = min(bottom_bound, hy + hh)
        hy, hh = cy0, max(0.0, cy1 - cy0)
        hy, hh = int(round(hy)), int(round(hh))
        if hw <= 0 or hh <= 0:
            return None
        return (hx, hy, hw, hh)

    def _draw_rows(self, layout: Dict[str, Any], clip_rect: Optional[Tuple[int, int, int, int]] = None) -> None:
        ix, iy, iw, ih = layout["ix"], layout["iy"], layout["iw"], layout["ih"]
        text_ix = layout["text_ix"]
        row_height = layout["row_height"]
        row_pitch = layout["row_pitch"]
        scroll = self._scroll_position
        clip_x0 = clip_y0 = clip_x1 = clip_y1 = None
        if clip_rect is not None:
            clip_x0, clip_y0, clip_w, clip_h = clip_rect
            clip_x1 = clip_x0 + clip_w
            clip_y1 = clip_y0 + clip_h
        for row in layout["rows"]:
            row_y = iy + row["offset"] - scroll * row_pitch
            row_x0 = ix
            row_y0 = row_y
            row_x1 = ix + iw
            row_y1 = row_y + row_height
            # A row straddling the BOTTOM edge still draws its visible
            # sliver instead of being blanked out entirely, so a partially-
            # visible next row peeks into view like a native scrollable
            # list, rather than only ever showing whole rows with dead
            # space below the last one. The TOP edge stays strict
            # (full-containment only, same as before) -- unlike the
            # bottom, there's something else (the header) sitting directly
            # above this widget's own bounds, and any row scrolling
            # partially above iy has to be erased again once it scrolls
            # further (nothing else ever repaints that strip), which
            # cleared into -- and permanently wiped -- the header instead
            # of just this widget's own content.
            if row_y < iy or row_y >= iy + ih:
                continue
            if clip_rect is not None and (row_x1 <= clip_x0 or row_y1 <= clip_y0 or row_x0 >= clip_x1 or row_y0 >= clip_y1):
                continue
            icon = row["icon"]
            if icon is not None:
                # Same "- 1" nudge as the text centering above (see
                # "centering" in _ensure_layout_cache) -- without it the
                # icon sits 1px lower than the label it's next to, since
                # only the text side of the row was ever getting that
                # adjustment.
                icon_y = row_y + max(0, (row_height - icon.height) // 2 - 1)
                self._gfx.draw_image(icon, ix, int(round(icon_y)))
            self._gfx.draw_text(row["label"], text_ix, int(round(row_y + row["centering"])), font=layout["font"])
            # A bottom-peeking row (see the check above) draws its icon/
            # text at their normal, un-clipped position -- draw_image/
            # draw_text have no clip mask, so whichever part of that ink
            # falls past iy+ih paints there anyway. Trimmed right back off
            # here rather than left in place: that ink sits outside the
            # area this widget's own clear_area(self.x, self.y, self.width,
            # self.height) sweeps on every later redraw, so left alone it
            # would never get erased again once the row scrolls elsewhere
            # -- a permanent ghost, not just a one-frame overdraw.
            if row_y1 > iy + ih:
                self._gfx.clear_area(ix, iy + ih, iw, int(round(row_y1 - (iy + ih))))

    def _draw_highlight(self, layout: Dict[str, Any]) -> Optional[Tuple[int, int, int, int]]:
        highlight = self._current_highlight_rect(layout)
        if highlight is None:
            return None
        hx, hy, hw, hh = highlight
        self._gfx.invert_area(hx, hy, hw, hh)
        self._gfx.invert_area(hx, hy, 1, 1)
        self._gfx.invert_area(hx + hw - 1, hy, 1, 1)
        self._gfx.invert_area(hx, hy + hh - 1, 1, 1)
        self._gfx.invert_area(hx + hw - 1, hy + hh - 1, 1, 1)
        return highlight

    def _content_rect(self) -> Tuple[int, int, int, int]:
        inset = self.border + self.padding
        ix = self.x + inset
        iy = self.y + inset
        iw = max(0, self.width - 2 * inset)
        ih = max(0, self.height - 2 * inset)
        return ix, iy, iw, ih

    def set_items(self, items: List[Any]) -> None:
        self._set_items(items)
        self.draw()

    def invalidate_draw_cache(self) -> None:
        self._last_draw_state = None

    def set_selected_index(self, index: int) -> None:
        """Programmatically move the selection (e.g. restoring a
        previously-saved position) without animating — snaps _visual_row
        and _scroll_position to match immediately, unlike handle_key's UP/
        DOWN which glide via a tween. Setting .selected_index directly
        does NOT do this: _visual_row stays at whatever it was (0.0 at
        construction), so the highlight rectangle keeps drawing at its old
        position even though .selected_index has moved — always go through
        this method instead of assigning .selected_index yourself."""
        if not self.items:
            return
        self.selected_index = max(0, min(index, len(self.items) - 1))
        self._scroll_position = self._target_scroll()
        self._visual_row = float(self.selected_index)
        self._highlight_tween = None
        self._scroll_tween = None
        self._highlight_from_index = self.selected_index
        self._highlight_to_index = self.selected_index

    def handle_key(self, keycode: str) -> bool:
        if not self.items:
            return False
        if keycode in ("KEY_UP", "KEY_W"):
            previous, previous_scroll = self.selected_index, self._scroll_position
            self.selected_index = max(0, self.selected_index - 1)
            if self.selected_index == previous:
                self._start_shake(-1)
                self.draw()
                return True
            self._start_highlight_move(previous, previous_scroll)
            self.draw()
            if self.on_change:
                self.on_change(self.selected_item)
            return True
        if keycode in ("KEY_DOWN", "KEY_S"):
            previous, previous_scroll = self.selected_index, self._scroll_position
            self.selected_index = min(len(self.items) - 1, self.selected_index + 1)
            if self.selected_index == previous:
                self._start_shake(1)
                self.draw()
                return True
            self._start_highlight_move(previous, previous_scroll)
            self.draw()
            if self.on_change:
                self.on_change(self.selected_item)
            return True
        if keycode == "KEY_ENTER":
            if self.on_select:
                self.on_select(self.items[self.selected_index])
            return True
        return False

    def _visible_rows(self) -> int:
        layout = self._ensure_layout_cache()
        return layout["visible_rows"]

    def _target_scroll(self) -> float:
        """Where _scroll_position needs to end up (in absolute row units)
        so selected_index is actually in view -- doesn't move it there
        itself, just reports the target, so callers can choose to animate
        toward it (_start_highlight_move) or snap directly
        (set_selected_index)."""
        visible = self._visible_rows()
        target = self._scroll_position
        if self.selected_index < target:
            target = float(self.selected_index)
        elif self.selected_index > target + visible - 1:
            target = float(self.selected_index - visible + 1)
        return max(0.0, target)

    def _start_highlight_move(self, previous_index: int, previous_scroll: float) -> None:
        if previous_index == self.selected_index:
            return
        target_row = float(self.selected_index)
        target_scroll = self._target_scroll()
        if self._tween_factory is None:
            self._visual_row = target_row
            self._scroll_position = target_scroll
            self._highlight_tween = None
            self._scroll_tween = None
            self._highlight_from_index = self._highlight_to_index = self.selected_index
            return
        # Only use the "settle" easing (e.g. an overshoot/bounce curve)
        # when this move starts from a full stop -- if a previous
        # highlight tween is still mid-flight, we're being retriggered by
        # rapid UP/DOWN repeats ("zooming" through the list), and bouncing
        # on every single intermediate hop reads as jittery rather than
        # springy. Falls back to the plain highlight_easing in that case,
        # reserving the bounce for whichever hop actually turns out to be
        # last (nothing interrupts it before it reaches the end of its own
        # curve).
        already_moving = self._highlight_tween is not None and not self._highlight_tween.done
        easing = self._highlight_easing if already_moving or self._highlight_settle_easing is None else (
            self._highlight_settle_easing
        )
        from_row = float(previous_index)
        self._highlight_tween = self._tween_factory(
            from_row, target_row, duration=self._highlight_duration, easing=easing
        )
        self._visual_row = from_row
        # The viewport scrolls smoothly right alongside the highlight
        # (same duration/easing) instead of snapping the instant selection
        # moves out of the previously-visible window -- rows used to jump
        # straight to their new position while only the highlight glided,
        # visibly detaching it from "the rows sliding past underneath it"
        # (this comment's old home). Both animate together now, so there's
        # nothing left to detach from.
        if target_scroll != previous_scroll:
            self._scroll_tween = self._tween_factory(
                previous_scroll, target_scroll, duration=self._highlight_duration, easing=easing
            )
            self._scroll_position = previous_scroll
        else:
            self._scroll_tween = None
        # Remembered so draw() can size the highlight box by LERPing
        # between the FROM and TO item's own ink dimensions across the
        # move, using the same eased fraction driving _visual_row's
        # position -- previously draw() picked whichever item was nearest
        # the current (rounded) _visual_row, so the box's WIDTH/HEIGHT
        # snapped abruptly mid-glide the instant rounding crossed from one
        # row to the other, instead of resizing smoothly alongside the
        # position tween.
        self._highlight_from_index = previous_index
        self._highlight_to_index = self.selected_index

    def _start_shake(self, direction: int) -> None:
        self._shake_elapsed = 0.0
        self._shake_active = True
        self._shake_direction = direction

    def _shake_progress(self) -> float:
        """0..1 shrink fraction for the current shake moment: 0 at the
        start/end, 1 at the midpoint -- draw() multiplies this by
        _SHAKE_AMPLITUDE and subtracts it from the halo's height (see its
        docstring for why height-and-anchor beats offsetting the whole
        box's position + clamping)."""
        if not self._shake_active:
            return 0.0
        # Clamp to 1.0 -- a tick's dt landing past _SHAKE_DURATION (always
        # true on whichever tick ends the shake, and easy to hit at low
        # frame rates where dt is coarse) would otherwise push t above 1,
        # and sin(pi * t) for t > 1 goes NEGATIVE -- a brief reversal/
        # glitch right at the tail end of every shake instead of a clean
        # stop at 0.
        t = min(1.0, self._shake_elapsed / self._SHAKE_DURATION)
        # Single half-sine hump: 0 at t=0, peaks (at 1.0) at t=0.5, back to
        # exactly 0 at t=1 -- one shrink-and-return, not a repeating wiggle.
        return math.sin(math.pi * t)

    def tick(self, dt: float) -> None:
        """Advance the highlight-move, scroll, and/or edge-of-list shake
        animations. Call once per frame from the owning app's update() --
        a no-op if none of them are currently animating (the common case,
        most frames)."""
        moved = False
        if self._highlight_tween is not None:
            self._highlight_tween.update(dt)
            self._visual_row = self._highlight_tween.value
            moved = True
            if self._highlight_tween.done:
                self._highlight_tween = None
        if self._scroll_tween is not None:
            self._scroll_tween.update(dt)
            self._scroll_position = self._scroll_tween.value
            moved = True
            if self._scroll_tween.done:
                self._scroll_tween = None
        if self._shake_active:
            self._shake_elapsed += dt
            if self._shake_elapsed >= self._SHAKE_DURATION:
                self._shake_active = False
            moved = True
        if moved:
            self.draw()

    def measure(self, available_w: int, available_h: int) -> Tuple[int, int]:
        inset = 2 * (self.margin + self.border + self.padding)
        n = len(self.items)
        # n rows at row_pitch apart, minus the one trailing gap after the
        # last row that spacing doesn't actually add (same n-1-gaps
        # convention as row_pitch/Row/Column's `spacing`).
        rows_h = n * self.row_pitch - self.spacing if n > 0 else self.row_height
        content_h = max(self.row_height, rows_h) + inset
        return (available_w, min(available_h, content_h) if available_h else content_h)

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        x += self.margin
        y += self.margin
        width = max(0, width - 2 * self.margin)
        height = max(0, height - 2 * self.margin)
        self.x, self.y, self.width, self.height = x, y, width, height
        self.bounds = Box(x, y, width, height)

    def animation_bounds(self) -> Tuple[int, int, int, int]:
        p = self.selected_padding
        return (self.x, self.y - p, self.width, self.height + 2 * p)

    # Halo padding around the selected row's highlight rectangle -- drawn
    # manually (see draw()) rather than via draw_text_inverted, whose own
    # padding halo is clamped to never extend above/left of the (x, y) it's
    # given (to protect a caller sitting flush at a hard edge, e.g. row 0
    # with no margin above it, from bleeding into a sibling above). Now
    # that ink always starts exactly at the nominal (x, y) — see
    # display_gfx._top_overhang's docstring — that clamp fires on
    # essentially every call, zeroing the top/left padding while leaving
    # the full amount on bottom/right: verified as a visibly asymmetric
    # highlight (0px top, 2px right, 1px bottom, 0px left) around a
    # selected item. Menu already has its own padding/border clearance
    # from its own edges, so it doesn't need that defensive clamp at
    # all — drawing the highlight rect directly gives an exact, symmetric
    # halo on all four sides instead.
    SELECTED_HALO_PADDING = 1

    def _clip_label(self, text: str, width: int, font) -> str:
        """Character-truncate `text` (with a trailing "...") if it's wider
        than `width` -- Menu never wrapped row text to begin with, so a
        label that happens to reach (or, after a padding/inset tweak,
        newly exceed) the row's right edge draws straight past it. Ink
        outside Menu's own clear_area(self.x, self.y, self.width, ...)
        rect never gets erased on the next redraw (nothing else owns that
        strip), leaving a permanent ghost sliver -- same failure mode
        TextBox._clip_to_width fixes for wrapped text, just for Menu's
        single-line rows instead."""
        if width <= 0:
            return ""
        if self._measure_text_size(text, font)[0] <= width:
            return text
        while text and self._measure_text_size(text + "...", font)[0] > width:
            text = text[:-1]
        return f"{text}..." if text else ""

    def draw(self) -> None:
        layout = self._ensure_layout_cache()
        current_scroll = self._scroll_position
        current_highlight = self._current_highlight_rect(layout)
        previous_state = self._last_draw_state
        can_partial = (
            previous_state is not None
            and previous_state.get("layout_key") == self._layout_cache_key
            and previous_state.get("scroll") == current_scroll
            and previous_state.get("inverted") == self.inverted
            and previous_state.get("border") == self.border
            and previous_state.get("highlight") is not None
            and current_highlight is not None
            and not self._shake_active
            and not previous_state.get("shake_active")
        )

        if can_partial:
            prev_highlight = previous_state["highlight"]
            dirty_x0 = min(prev_highlight[0], current_highlight[0])
            dirty_y0 = min(prev_highlight[1], current_highlight[1])
            dirty_x1 = max(prev_highlight[0] + prev_highlight[2], current_highlight[0] + current_highlight[2])
            dirty_y1 = max(prev_highlight[1] + prev_highlight[3], current_highlight[1] + current_highlight[3])
            dirty_rect = (dirty_x0, dirty_y0, dirty_x1 - dirty_x0, dirty_y1 - dirty_y0)
            self._gfx.clear_area(*dirty_rect)
            self._draw_rows(layout, clip_rect=dirty_rect)
            current_highlight = self._draw_highlight(layout)
            if self.inverted:
                self._gfx.invert_area(*dirty_rect)
        else:
            # The selection halo is allowed to overhang the content rect
            # by selected_padding px at the very first/last row (see the
            # ±p in top_bound/bottom_bound above) -- that's its normal,
            # permanent resting look there, not just a transient scroll
            # artifact. self.height alone doesn't reach that overhang, so
            # a later full redraw (e.g. once scrolling moves the selection
            # away) never erased it -- a permanent 1px ghost just outside
            # this widget's own box.
            p = self.selected_padding
            self._gfx.clear_area(self.x, self.y - p, self.width, self.height + 2 * p)
            self._draw_rows(layout)
            current_highlight = self._draw_highlight(layout)
            if self.inverted:
                self._gfx.invert_area(self.x, self.y, self.width, self.height)
            if self.border > 0:
                self._draw_border()

        self._last_draw_state = {
            "layout_key": self._layout_cache_key,
            "scroll": current_scroll,
            "highlight": current_highlight,
            "inverted": self.inverted,
            "border": self.border,
            "shake_active": self._shake_active,
        }

    def _draw_border(self) -> None:
        b = self.border
        x, y, w, h = self.x, self.y, self.width, self.height
        fill = 0 if self.inverted else 255
        self._gfx.draw_area(x, y, w, b, fill=fill)
        self._gfx.draw_area(x, y + h - b, w, b, fill=fill)
        self._gfx.draw_area(x, y, b, h, fill=fill)
        self._gfx.draw_area(x + w - b, y, b, h, fill=fill)
        # Punch the 4 outer corner pixels back to background -- a bare
        # rectangle reads as harshly boxy on a 128x64 1-bit display;
        # chamfering just the single corner pixel softens it into a
        # rounded-looking frame without touching the (odd-numbered)
        # border thickness itself.
        bg = 255 - fill
        self._gfx.draw_area(x, y, 1, 1, fill=bg)
        self._gfx.draw_area(x + w - 1, y, 1, 1, fill=bg)
        self._gfx.draw_area(x, y + h - 1, 1, 1, fill=bg)
        self._gfx.draw_area(x + w - 1, y + h - 1, 1, 1, fill=bg)

    @property
    def selected_item(self) -> Optional[MenuItem]:
        if not self.items:
            return None
        return self.items[self.selected_index]


class TextField:
    """Wraps a core_os.packages.input.text_input.TextInput with word-wrapped rendering — the
    buffer (plus its inline [suggestion]) wraps across multiple lines as you
    type, the same way ScrollPanel wraps static text, instead of running off
    the edge of the screen on one line.

    display_transform, if given, is applied to the buffer before
    wrapping/drawing. Suggestions are still accepted as raw typed text by
    TextInput, but are display-transformed here too so Japanese mode can
    show kana suggestions instead of romaji without changing input/storage
    behavior.

    Draws a blinking caret at text_input.cursor. Call tick() from the app's
    update() loop to actually make it blink while idle — draw() alone only
    runs on keystrokes, which would leave the caret frozen solid (or
    invisible) between them. tick() is cheap: it only touches the caret's
    own tiny rect, not a full redraw.

    Cursor position under display_transform (Japanese romaji -> kana) is an
    approximation: the raw buffer index is mapped to a display-text index
    by re-running the transform on just the prefix up to the cursor. That's
    exact once a mora has fully resolved, but can be off by a character
    while sitting mid-mora (e.g. right after typing a lone "k" that's about
    to become part of "kka") since the transform's own lookahead hasn't
    resolved that prefix the same way it will once more is typed. Self-
    corrects the instant the mora resolves; a real index-mapping IME is out
    of scope here.
    """

    CURSOR_BLINK_INTERVAL = 0.5

    def __init__(
        self,
        gfx,
        text_input,
        x: int = 0,
        y: int = 0,
        width: int = 128,
        font=None,
        display_transform=None,
        valign: str = "start",
    ) -> None:
        self._gfx = gfx
        self.text_input = text_input
        self.x, self.y, self.width = x, y, width
        self.height = 0
        self.bounds = Box(x, y, width, 0)
        self.font = font or gfx.fonts["small"]
        self.display_transform = display_transform
        self.valign = valign if valign in ("start", "center", "end") else "start"
        self._drawn_height = self.line_height
        self._cursor_rect = None  # (x, y, w, h) of the caret, or None
        self._cursor_visible = True
        self._last_blink = time.time()
        self._wrap_cache_key = None
        self._wrap_cache: Optional[List[str]] = None

    def _displayed_text(self) -> str:
        text = self.text_input.buffer
        return self.display_transform(text) if self.display_transform else text

    @property
    def line_height(self) -> int:
        # Measured fresh each time (not cached at construction, so it
        # stays correct if the active font changes, e.g. Japanese mode)
        # against the actual displayed text, not a fixed "Ag" reference
        # -- see display_gfx.line_height's docstring for why a fixed
        # reference leaves unwanted gap under script-specific text.
        return self._gfx.line_height(self._displayed_text(), self.font)

    def _content_height(self, lines: List[str], text: str) -> int:
        # (n-1) inter-line gaps + one line's own glyph height, NOT
        # n * line_height -- multiplying by n reserves a trailing gap
        # after the LAST line that nothing follows (see
        # display_gfx.line_height's docstring).
        if not lines:
            return 0
        _, glyph_h = self._gfx.get_text_size(text or "Ag", self.font)
        return (len(lines) - 1) * self.line_height + glyph_h

    def measure(self, available_w: int, available_h: int) -> Tuple[int, int]:
        text = self._displayed_text()
        lines = self._wrap(text) if text else [""]
        return (available_w, self._content_height(lines, text))

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height
        self.bounds = Box(x, y, width, height)

    def handle_key(self, keycode: str) -> bool:
        consumed = self.text_input.handle_key(keycode)
        self.draw()
        return consumed

    def tick(self) -> None:
        """Call from the app's update() loop to blink the caret while idle."""
        now = time.time()
        if now - self._last_blink < self.CURSOR_BLINK_INTERVAL:
            return
        self._last_blink = now
        self._cursor_visible = not self._cursor_visible
        self._draw_cursor()

    def _draw_cursor(self) -> None:
        if not self._cursor_rect:
            return
        x, y, w, h = self._cursor_rect
        if self._cursor_visible:
            self._gfx.draw_area(x, y, w, h, fill=255)
        else:
            self._gfx.clear_area(x, y, w, h)

    def _wrap(self, text: str) -> List[str]:
        """Word-wrap `text` to self.width, preserving EXACT original
        spacing — unlike the shared gfx.wrap_text (which every other
        widget here uses), this does NOT collapse whitespace runs via
        text.split(). _row_col_for_index maps a raw buffer index straight
        onto these wrapped lines by length, so if wrapping shortened the
        text (e.g. a double space collapsed to one — very easy to type by
        accident), that mapping silently desyncs: a raw index into the
        ORIGINAL text no longer lines up with the same offset into the
        SHORTER wrapped text, landing the cursor a word or more away from
        where it actually is. Concatenating this method's own output
        (with no separator — whitespace stays attached to whichever line
        it was already on) reconstructs `text` exactly, character for
        character, so that mapping stays correct no matter how irregular
        the spacing is."""
        cache_key = (text, self.width, id(self.font), id(self.display_transform))
        if self._wrap_cache_key == cache_key and self._wrap_cache is not None:
            return self._wrap_cache
        if not text:
            result = [""]
            self._wrap_cache_key = cache_key
            self._wrap_cache = result
            return result
        tokens = re.findall(r"\S+|\s+", text)
        lines: List[str] = []
        current = ""
        for token in tokens:
            if token.isspace():
                # Whitespace never triggers a wrap by itself -- it just
                # stays attached to whatever line it's already on.
                current += token
                continue
            trial = current + token
            w, _ = self._gfx.get_text_size(trial, self.font)
            if w > self.width and current.strip():
                lines.append(current)
                current = token
            else:
                current = trial
        lines.append(current)
        self._wrap_cache_key = cache_key
        self._wrap_cache = lines
        return lines

    def _advance_width(self, text: str) -> int:
        """Width to advance the cursor (or suggestion) past `text`.

        measure_ink alone undercounts this whenever `text` ends in one or
        more spaces: spaces paint no pixels, so a render-and-scan tight
        bbox (measure_ink) trims them off the end entirely, same as it
        trims any other invisible edge padding — verified: measure_ink
        treats "Hello", "Hello ", and "Hello   " as identical, so typing
        or moving the cursor past a trailing space never advanced it at
        all. get_text_size (the font's own metric-based width) doesn't
        have that problem, since it isn't derived from rendered pixels —
        and its own known issue (the last VISIBLE glyph's ink not filling
        its full advance width, see get_text_size's docstring) can't
        apply to a trailing space either, since there's no ink there to
        under/overshoot — confirmed against a direct pixel scan (ground
        truth: where the next real character's ink actually starts after
        "Hello ") that get_text_size gets this exactly right. So: tight
        ink measurement when there's real ink to be tight around, plain
        metric width when the text ends on invisible whitespace."""
        if not text:
            return 0
        if text.endswith(" "):
            w, _ = self._gfx.get_text_size(text, self.font)
            return w
        w, _ = self._gfx.measure_ink(text, self.font)
        return w

    # Same fix, same reasoning as Menu.SELECTED_HALO_PADDING: drawn
    # manually instead of via draw_text_inverted, whose padding halo (a)
    # clamps to never extend above/left of the given (x, y) -- which now
    # that ink always starts exactly at the nominal y fires on every call,
    # leaving an asymmetric highlight -- and (b) sizes itself from
    # get_text_size's metric-based width, which can overshoot the
    # actually-painted ink by a pixel for this font (see
    # display_gfx.measure_ink's docstring). Drawing the highlight rect
    # directly from measure_ink gives an exact, symmetric halo instead.
    #
    # Also used for the caret's own height (see draw()) so it visually
    # matches the suggestion highlight it sits next to: 1px taller/shorter
    # than the glyph on both top and bottom rather than exactly glyph-tight.
    HALO_PADDING = 0

    # Purely cosmetic nudge: the suggestion highlight sits this many extra
    # pixels right of where it'd otherwise start (right after the typed
    # text/at the row start) — separate from HALO_PADDING, which pads the
    # highlight symmetrically around whatever text it wraps rather than
    # shifting its start position.
    SUGGESTION_X_OFFSET = 1

    def _draw_suggestion(
        self,
        text: str,
        x: int,
        y: int,
        line_text_for_height: Optional[str] = None,
        box_height: Optional[int] = None,
    ) -> None:
        # ink_bbox, not get_text_size, for the whole box: ink_left compensates
        # any left-bearing gap (see display_gfx.ink_bbox's docstring), and
        # ink_h avoids get_text_size's metric height overshooting the real
        # painted glyphs by a pixel (same overshoot Menu's selection halo
        # hit -- verified for misaki_gothic.ttf too, not just the old fonts).
        ink_left, _, ink_w, _ = self._gfx.ink_bbox(text, self.font)
        if box_height is not None:
            ink_h = max(0, box_height)
        else:
            height_text = line_text_for_height if line_text_for_height is not None else text
            _, _, _, ink_h = self._gfx.ink_bbox(height_text, self.font)
        p = self.HALO_PADDING
        # Cosmetic balance tweak: extend the LEFT edge by 1px and also add
        # 1px on the RIGHT edge to keep the box visually balanced.
        self._gfx.draw_area(x + ink_left - p - 1, y - p, ink_w + 2 * p + 2, ink_h + 2 * p, fill=255)
        self._gfx.draw_text(text, x, y, font=self.font, fill=0)

    @staticmethod
    def _row_col_for_index(lines, index: int) -> Tuple[int, int]:
        """Which (row, col) in `lines` does character offset `index`
        (into the ORIGINAL, unwrapped text) fall at? No separator to
        account for between lines -- _wrap's lines concatenate back into
        the original text exactly (whitespace stays attached to whichever
        line it was already on), unlike a naive rejoin-with-one-space."""
        consumed = 0
        for row, line in enumerate(lines):
            if index <= consumed + len(line):
                return row, index - consumed
            consumed += len(line)
        last_row = len(lines) - 1
        return last_row, len(lines[last_row])

    def draw(self) -> None:
        raw_text = self.text_input.buffer
        text = self.display_transform(raw_text) if self.display_transform else raw_text
        suggestion = getattr(self.text_input, "suggestion", "")
        display_suggestion = suggestion
        if self.display_transform and suggestion:
            transformed_full = self.display_transform(raw_text + suggestion)
            if transformed_full.startswith(text):
                display_suggestion = transformed_full[len(text):]
            else:
                # IME transforms can rewrite unresolved tails in-place
                # (e.g. "かn" + "a" => "かな"), so derive the rendered
                # suggestion from the transformed full text delta at the
                # longest shared prefix, not from transforming the suffix
                # alone.
                shared = 0
                limit = min(len(text), len(transformed_full))
                while shared < limit and text[shared] == transformed_full[shared]:
                    shared += 1
                display_suggestion = transformed_full[shared:]

        lines = self._wrap(text)

        # Does the rendered suggestion fit after the last wrapped line, or
        # does it need a line of its own? Mirrors V1's proxi app, which also
        # had to decide "same line vs. next line" for the suggestion.
        last_line = lines[-1]
        last_line_w, _ = self._gfx.get_text_size(last_line, self.font)
        suggestion_w, _ = self._gfx.get_text_size(display_suggestion, self.font) if display_suggestion else (0, 0)
        # Include the visual rightward nudge used when drawing the
        # suggestion itself, otherwise edge-case suggestions get classified
        # as "fits" but render 1-2px outside the field.
        suggestion_fits_same_line = bool(display_suggestion) and (
            last_line_w + self.SUGGESTION_X_OFFSET + suggestion_w <= self.width
        )
        extra_line = bool(display_suggestion) and not suggestion_fits_same_line
        total_rows = len(lines) + (1 if extra_line else 0)

        # Row spacing/centering must consider suggestion glyph metrics too,
        # otherwise a suggestion containing taller/descender glyphs can be
        # drawn lower than the field's assumed content height and look
        # clipped at the bottom.
        _, text_glyph_h = self._gfx.get_text_size(text or "Ag", self.font)
        suggestion_line_height = self._gfx.line_height(display_suggestion, self.font) if display_suggestion else self.line_height
        row_line_height = max(self.line_height, suggestion_line_height)
        _, suggestion_glyph_h = self._gfx.get_text_size(display_suggestion, self.font) if display_suggestion else (0, 0)
        last_row_glyph_h = suggestion_glyph_h if extra_line else max(text_glyph_h, suggestion_glyph_h)

        # Map the raw-buffer cursor index to a display-text index (see
        # class docstring re: display_transform), then to a wrapped (row,
        # col) — needed both to draw the caret and to decide what to scroll
        # into view below.
        raw_cursor = getattr(self.text_input, "cursor", len(self.text_input.buffer))
        display_cursor = len(self.display_transform(self.text_input.buffer[:raw_cursor])) if self.display_transform else raw_cursor
        cursor_row, cursor_col = self._row_col_for_index(lines, display_cursor)

        # Clip to whatever height our layout parent actually allocated
        # (self.height == 0 means "not laid out" / standalone use, so fall
        # back to showing everything, matching the old unclipped behavior).
        # Scroll to keep the CURSOR's row visible — usually that's also the
        # end (what you just typed), but once you've moved the cursor back
        # into earlier wrapped lines with KEY_LEFT, those need to scroll
        # into view too rather than staying hidden above a window that's
        # still pinned to the end. Without clipping at all, content taller
        # than our allotted region would draw over whatever sits below us
        # (e.g. proxi's hint label), and nothing would ever repair that
        # once the content shrank back down, since only this widget
        # redraws on keystroke, not its layout siblings.
        max_visible = max(1, self.height // row_line_height) if self.height else total_rows
        # (n-1) inter-line gaps + one line's worth of height, not
        # n * line_height (see display_gfx.line_height's docstring) --
        # the extra suggestion row (if any) costs one more full row since
        # a real gap does separate it from the wrapped lines above it.
        clip_height = (
            self.height
            if self.height
            else (((total_rows - 1) * row_line_height) + last_row_glyph_h if total_rows > 0 else 0)
        )
        first_row = max(0, min(cursor_row, total_rows - max_visible))

        # Inset by HALO_PADDING on every side: _draw_suggestion's halo (and
        # now the caret, sized to match it — see draw() below) intentionally
        # extend that many pixels beyond the text/glyph they wrap (for a
        # symmetric look — see _draw_suggestion's docstring), which means
        # they can land up to that far outside this widget's own (self.x,
        # self.y, self.width, height) rect — e.g. a suggestion or caret on
        # the very first row draws 1px above self.y. Without this, that
        # sliver falls outside clear_area's swept region and never gets
        # wiped on a later redraw where the suggestion/caret has moved or
        # gone away, leaving a stale fragment behind (verified: the top row
        # of the highlight box stopped clearing while typing). The right
        # side gets SUGGESTION_X_OFFSET on top of that, since the
        # suggestion's own rightward nudge can push it that much further
        # past self.width too.
        p = self.HALO_PADDING
        right_pad = p + self.SUGGESTION_X_OFFSET
        clear_h = self.height if self.height else max(self._drawn_height, clip_height)
        self._gfx.clear_area(self.x - p, self.y - p, self.width + p + right_pad, clear_h + 2 * p)
        self._drawn_height = clip_height

        self._cursor_rect = None
        visible_rows = max(0, min(total_rows, first_row + max_visible) - first_row)
        visible_h = ((visible_rows - 1) * row_line_height + last_row_glyph_h) if visible_rows > 0 else 0
        y_offset = 0
        if self.height:
            free_h = max(0, self.height - visible_h)
            if self.valign == "center":
                y_offset = free_h // 2
            elif self.valign == "end":
                y_offset = free_h
        for display_row, source_row in enumerate(range(first_row, min(total_rows, first_row + max_visible))):
            y = self.y + y_offset + display_row * row_line_height
            if source_row < len(lines):
                self._gfx.draw_text(lines[source_row], self.x, y, font=self.font)
                if display_suggestion and suggestion_fits_same_line and source_row == len(lines) - 1:
                    # Inverted (white background, black text) highlight —
                    # the same look V1's proxi app used for its autocomplete
                    # suggestion via draw_highlighted_text's bracketed-
                    # segment handling. _advance_width (not get_text_size,
                    # aka last_line_w, which is fine for the fits-same-line
                    # BUDGET check above but not for POSITIONING), so the
                    # suggestion starts flush against the real rendered
                    # text — including any trailing space(s) before it.
                    self._draw_suggestion(
                        display_suggestion,
                        self.x + self._advance_width(lines[source_row]) + self.SUGGESTION_X_OFFSET,
                        y,
                        line_text_for_height=lines[source_row] + display_suggestion,
                        box_height=row_line_height,
                    )
                if source_row == cursor_row:
                    # _advance_width, not get_text_size or measure_ink
                    # alone: verified the caret sitting a pixel right of
                    # where the prefix's rendered ink ends (get_text_size),
                    # and separately not moving at all past a trailing
                    # space (measure_ink, which can't see space characters
                    # at all — see _advance_width's docstring).
                    prefix_w = self._advance_width(lines[source_row][:cursor_col])
                    p = self.HALO_PADDING
                    self._cursor_rect = (self.x + prefix_w, y - p, 1, row_line_height + 2 * p)
            else:
                # The suggestion's own dedicated row (extra_line case).
                self._draw_suggestion(
                    display_suggestion,
                    self.x + self.SUGGESTION_X_OFFSET,
                    y,
                    box_height=row_line_height,
                )

        # Redraw always leaves the caret solid-visible; it only starts
        # blinking again once tick() sees CURSOR_BLINK_INTERVAL of idle time.
        self._cursor_visible = True
        self._last_blink = time.time()
        self._draw_cursor()


class Dialog:
    """A modal yes/no confirmation prompt, drawn on the overlay layer, sized
    to fit its actual title/message text at the current font metrics and
    centered on the display — rather than a fixed box tuned for one font,
    which would either clip or float oddly-positioned once text metrics
    change (e.g. misaki_gothic.ttf's taller kana glyphs)."""

    def __init__(
        self,
        gfx,
        title: str,
        message: str,
        on_yes: Optional[Callable[[], None]] = None,
        on_no: Optional[Callable[[], None]] = None,
        padding: int = 4,
    ) -> None:
        self._gfx = gfx
        self.title = title
        self.message = message
        self.on_yes = on_yes
        self.on_no = on_no
        self.padding = padding
        self.bounds = Box()

    def _compute_box(self) -> Tuple[int, int, int, int]:
        font = self._gfx.fonts["small"]
        title_w, title_h = self._gfx.get_text_size(self.title, font)
        msg_w, msg_h = self._gfx.get_text_size(self.message, font)
        w = max(title_w, msg_w) + self.padding * 2
        h = title_h + msg_h + self.padding * 3
        display = self._gfx.resources.core.display
        x = max(0, (display.width - w) // 2)
        y = max(0, (display.height - h) // 2)
        return (x, y, w, h)

    @classmethod
    def confirm(cls, gfx, title: str, message: str, on_yes=None, on_no=None) -> "Dialog":
        dialog = cls(gfx, title, message, on_yes, on_no)
        dialog.draw()
        return dialog

    def handle_key(self, keycode: str) -> bool:
        if keycode in ("KEY_ENTER", "KEY_Y"):
            self.dismiss()
            if self.on_yes:
                self.on_yes()
            return True
        if keycode in ("KEY_ESC", "KEY_N"):
            self.dismiss()
            if self.on_no:
                self.on_no()
            return True
        return False

    def draw(self) -> None:
        x, y, w, h = self._compute_box()
        self.bounds = Box(x, y, w, h)
        font = self._gfx.fonts["small"]
        _, title_h = self._gfx.get_text_size(self.title, font)
        self._gfx.draw_overlay_area(x, y, w, h, fill=255)
        self._gfx.draw_overlay_text(self.title, x + self.padding, y + self.padding, font=font, fill=0)
        self._gfx.draw_overlay_text(
            self.message, x + self.padding, y + self.padding * 2 + title_h, font=font, fill=0
        )

    def dismiss(self) -> None:
        x, y, w, h = self.bounds.as_tuple() if self.bounds.width else self._compute_box()
        self._gfx.clear_overlay_area(x, y, w, h)


class ProgressBar:
    """Horizontal fill bar with an optional static `label` to its left and
    an optional value string to its right -- either the live percentage
    (show_percent=True) or any custom text via set_value_text (e.g. "3/10",
    "1.2 MB/s"); an explicit set_value_text always wins over show_percent
    if both are given. Both are measured fresh from the current font every
    draw (same convention as Label/Menu/ScrollPanel), so the bar itself
    shrinks to make room instead of either text overlapping it."""

    _GAP = 4

    def __init__(
        self, gfx, x: int = 0, y: int = 0, width: int = 0, height: int = 4, font=None,
        label: Optional[str] = None, show_percent: bool = False, value_text: Optional[str] = None,
    ) -> None:
        self._gfx = gfx
        self.x, self.y, self.width, self.height = x, y, width, height
        self._preferred_height = height
        self._progress = 0.0
        self.font = font
        self.label = label
        self.show_percent = show_percent
        self._value_text = value_text

    def _font(self):
        return self.font or self._gfx.fonts["small"]

    def set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, value))
        self.draw()

    def set_value_text(self, text: Optional[str]) -> None:
        """Overrides show_percent's auto-generated text -- pass None to go
        back to showing the live percentage (if show_percent is on) or
        nothing at all."""
        self._value_text = text
        self.draw()

    def _current_value_text(self) -> Optional[str]:
        if self._value_text is not None:
            return self._value_text
        if self.show_percent:
            return f"{int(round(self._progress * 100))}%"
        return None

    def _reserved(self, text: Optional[str]) -> int:
        if not text:
            return 0
        w, _ = self._gfx.get_text_size(text, self._font())
        return w + self._GAP

    def measure(self, available_w: int, available_h: int) -> Tuple[int, int]:
        text = self.label or self._current_value_text()
        h = self._preferred_height
        if text:
            h = max(h, self._gfx.line_height(text, self._font()))
        return (available_w, min(available_h, h) if available_h else h)

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height

    def draw(self) -> None:
        self._gfx.clear_area(self.x, self.y, self.width, self.height)
        font = self._font()

        value_text = self._current_value_text()
        label_reserved = self._reserved(self.label)
        value_reserved = self._reserved(value_text)

        bar_x = self.x + label_reserved
        bar_w = max(0, self.width - label_reserved - value_reserved)
        bar_h = min(self._preferred_height, self.height)
        bar_y = self.y + max(0, (self.height - bar_h) // 2)

        if self.label:
            _, label_h = self._gfx.get_text_size(self.label, font)
            self._gfx.draw_text(self.label, self.x, self.y + max(0, (self.height - label_h) // 2), font=font)

        filled = int(bar_w * self._progress)
        if filled > 0:
            self._gfx.draw_area(bar_x, bar_y, filled, bar_h)

        if value_text:
            value_w, value_h = self._gfx.get_text_size(value_text, font)
            value_x = self.x + self.width - value_w
            self._gfx.draw_text(value_text, value_x, self.y + max(0, (self.height - value_h) // 2), font=font)


class Toast:
    """Centralizes the loading/message/error screen convention every V1 app
    reimplemented ad hoc (AppBase.show_loading/show_message/show_error).
    Body text word-wraps to the display width and its start position is
    computed from the title's actual measured height, rather than a fixed
    y-offset that could either collide with a taller title font or leave
    an oddly large gap under a shorter one."""

    def __init__(self, gfx, padding: int = 4) -> None:
        self._gfx = gfx
        self.padding = padding

    def _wrap(self, text: str, width: int, font) -> List[str]:
        # Delegates to display_gfx.wrap_text rather than its own word-split
        # loop -- that shared implementation also breaks CJK text at
        # character boundaries (Japanese has no spaces to word-split on;
        # see its docstring), which this duplicate never did.
        return self._gfx.wrap_text(text, width, font)

    def _render(self, title: str, body: str) -> None:
        self._gfx.clear_screen()
        font = self._gfx.fonts["small"]
        display = self._gfx.resources.core.display
        content_w = display.width - self.padding * 2

        _, title_h = self._gfx.get_text_size(title, font)
        self._gfx.draw_text(title, self.padding, self.padding, font=font)

        body_y = self.padding * 2 + title_h
        y = body_y
        for line in self._wrap(body, content_w, font):
            # Per-line height, not a fixed "Ag" reference -- misaki_gothic.ttf's
            # kana fill their full 8px cell, 1px taller than "Ag", so a body
            # mixing English and Japanese lines needs each line's OWN height
            # (see display_gfx.Package.line_height) or the taller lines get
            # squeezed into a slot sized for the shorter Latin ones.
            line_h = self._gfx.line_height(line, font)
            if y + line_h > display.height:
                break
            self._gfx.draw_text(line, self.padding, y, font=font)
            y += line_h

    def loading(self, text: str) -> None:
        self._render("Loading...", text)

    def message(self, title: str, body: str, duration: Optional[float] = None) -> None:
        self._render(title, body)

    def error(self, text: str) -> None:
        self.message("Error", text)


class ScrollPanel:
    """Word-wraps `text` into one Label per line and hands them to a
    layout.Column(scroll=True) -- text scrolling is just an application of
    the same modular scroll primitive any Row/Column can opt into (see
    layout._Stack's `scroll` docstring), not a separate hand-rolled offset/
    clamp/key-handling implementation. Kept as its own class purely for the
    convenience of the single (gfx, x, y, width, height, text) constructor
    apps already use -- everything else delegates to the internal Column."""

    def __init__(self, gfx, x: int = 0, y: int = 0, width: int = 128, height: int = 64, text: str = "") -> None:
        self._gfx = gfx
        self.x, self.y, self.width, self.height = x, y, width, height
        self.bounds = Box(x, y, width, height)
        # spacing=1: a Label's measured height is the tight glyph height
        # (display_gfx.get_text_size), with no inter-line gap of its own --
        # the old line-offset implementation added that gap itself via
        # line_height() (glyph height + 1px); stacking Labels in a Column
        # needs the same 1px reproduced as `spacing` between rows instead.
        self._column = Column(gfx=gfx, scroll=True, spacing=1)
        # NOT self.set_text(text) -- that also draw()s, which at
        # construction time would run against whatever x/y/width/height
        # defaults were passed in rather than the real position a parent
        # layout assigns via set_bounds() moments later (same latent bug
        # documented on Menu.__init__ -- draw() only clear_area()s its OWN
        # bounds, so an errant first draw at the wrong rect can leave
        # stale pixels outside a later, correctly-positioned one). The
        # column DOES need its layout run once here though (set_bounds,
        # not draw) -- unlike the old line-offset implementation, which
        # computed everything fresh from self.x/y/width/height on every
        # draw() call, the Column needs an explicit layout pass before it
        # has anything to draw at all.
        self._set_text(text)
        self._column.set_bounds(x, y, width, height)

    def _set_text(self, text: str) -> None:
        self._text = text
        font = self._gfx.fonts["small"]
        # width - 1: Column(scroll=True) already reserves its own 1px
        # scrollbar gutter internally, but that reservation happens when
        # laying out children against ITS width, not when THIS text is
        # wrapped into lines up front -- pre-wrapping to the same reduced
        # width keeps a line's own measured width from exceeding the space
        # the Column will actually give its Label (see the "narrow to make
        # room" fix this mirrors).
        lines = self._gfx.wrap_text(text, self.width - 1, font) if text else []
        self._column.children = [_content(Label(self._gfx, line, font=font)) for line in lines]

    def set_text(self, text: str) -> None:
        self._set_text(text)
        self.set_bounds(self.x, self.y, self.width, self.height)
        self.draw()

    def measure(self, available_w: int, available_h: int) -> Tuple[int, int]:
        return self._column.measure(available_w, available_h)

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height
        self.bounds = Box(x, y, width, height)
        self._column.set_bounds(x, y, width, height)

    def handle_key(self, keycode: str) -> bool:
        return self._column.handle_key(keycode)

    def draw(self) -> None:
        self._column.draw()


class TextBox:
    """A wrapped block of text with an optional line cap (text beyond it
    is truncated with an ellipsis on the last visible line, rather than
    growing further — see proxi's speaking-status popup, the original
    motivating use case) plus the same CSS-box-model padding/margin/
    border/inverted knobs as layout._Stack (see its docstring): margin
    moves this widget's own bounds in, padding then moves the text in
    from the border, and inverted flips the whole box to black-on-white
    after drawing regardless of what was drawn.

    This exists so apps don't each hand-roll their own wrap+box widget
    directly against the raw display_gfx API — every fix that went into
    getting this right (line height measured against the real text, not
    a fixed "Ag" reference; (n-1) inter-line gaps rather than n; a real
    border/padding/margin split) now lives here once instead of being
    re-discovered per app."""

    def __init__(
        self,
        gfx,
        text: str = "",
        font=None,
        max_lines: Optional[int] = None,
        padding: int = 0,
        margin: int = 0,
        border: int = 0,
        inverted: bool = False,
        fill: bool = False,
    ) -> None:
        self._gfx = gfx
        self.text = text
        self.font = font
        self.max_lines = max_lines
        self.padding = padding
        self.margin = margin
        self.border = border
        self.inverted = inverted
        self.fill = fill
        self.x = self.y = self.width = self.height = 0
        self._wrap_cache_key = None
        self._wrap_cache: Optional[List[str]] = None

    def set_text(self, text: str) -> None:
        self.text = text

    def _font(self):
        return self.font or self._gfx.fonts["small"]

    def _wrap(self, available_w: int, max_lines: Optional[int] = None) -> List[str]:
        limit = self.max_lines if max_lines is None else max_lines
        font = self._font()
        cache_key = (self.text, available_w, limit, id(font))
        if self._wrap_cache_key == cache_key and self._wrap_cache is not None:
            return self._wrap_cache
        lines = self._gfx.wrap_text(self.text, available_w, font)
        if limit is None or len(lines) <= limit:
            self._wrap_cache_key = cache_key
            self._wrap_cache = lines
            return lines
        if limit <= 0:
            result: List[str] = []
            self._wrap_cache_key = cache_key
            self._wrap_cache = result
            return result

        # Overflow: keep the first `limit` lines and squeeze an
        # ellipsis onto the last one, dropping trailing words until
        # "<line>..." fits. Three ASCII periods, not the U+2026 "…"
        # character -- misaki_gothic.ttf does have a real "…" glyph, so
        # this is no longer the tofu-box/font-upgrade hazard it used to be
        # under the old split pixel.ttf/LanaPixel.ttf fonts, just a
        # pixel-width-consistency choice at this point.
        # Character-level, not word-level: Japanese has no spaces to drop
        # words at (a spaceless CJK line is one "word", so dropping it
        # loses the whole line in one step instead of trimming toward a
        # fit) -- same reasoning as _clip_to_width below, just applied to
        # this overflow-ellipsis case (which always appends "...", even if
        # the untruncated line would itself have fit, since there IS more
        # text beyond it) instead of the too-wide-single-word one.
        visible = lines[:limit]
        last = visible[-1]
        while last:
            candidate = last + "..."
            w, _ = self._gfx.get_text_size(candidate, font)
            if w <= available_w:
                visible[-1] = candidate
                break
            last = last[:-1]
        else:
            visible[-1] = "..."
        self._wrap_cache_key = cache_key
        self._wrap_cache = visible
        return visible

    def _clip_to_width(self, text: str, width: int, font) -> str:
        """Character-level fallback truncation for a single already-wrapped
        line that still doesn't fit `width` -- wrap_text() only breaks on
        whitespace (see its docstring), so a single word/token wider than
        the box on its own (a long author handle, an unbroken URL, CJK text
        with no spaces at all) sails straight past it undrawn-truncated,
        escaping this widget's bounds. _wrap()'s own ellipsis logic already
        guards the OVERFLOW-lines case (beyond max_lines) the same way, but
        per-word rather than per-character, so it doesn't help here since
        there's only one word and it's already too wide alone."""
        if self._gfx.get_text_size(text, font)[0] <= width:
            return text
        while text and self._gfx.get_text_size(text + "...", font)[0] > width:
            text = text[:-1]
        return f"{text}..." if text else ""

    def measure(self, available_w: int, available_h: int) -> Tuple[int, int]:
        if not self.text:
            return (available_w, 0)
        font = self._font()
        outer_w = max(0, available_w - 2 * self.margin)
        inset = self.border + self.padding
        lines = self._wrap(max(0, outer_w - 2 * inset))
        line_h = self._gfx.line_height(self.text, font)
        _, glyph_h = self._gfx.get_text_size(self.text, font)
        content_h = (len(lines) - 1) * line_h + glyph_h if lines else 0
        h = content_h + 2 * inset + 2 * self.margin
        return (available_w, min(available_h, h) if available_h else h)

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        # Margin first, same as layout._Stack.set_bounds: self.x/y/width/
        # height (this widget's "bounds") reflect the margined-in rect,
        # not the raw space the parent handed us.
        x += self.margin
        y += self.margin
        width = max(0, width - 2 * self.margin)
        height = max(0, height - 2 * self.margin)
        self.x, self.y, self.width, self.height = x, y, width, height

    def draw(self) -> None:
        if not self.text or self.height <= 0:
            return
        gfx = self._gfx
        gfx.clear_area(self.x, self.y, self.width, self.height)
        if self.fill:
            gfx.draw_area(self.x, self.y, self.width, self.height, fill=0)
        font = self._font()

        inset = self.border + self.padding
        inner_x = self.x + inset
        inner_y = self.y + inset
        inner_w = max(0, self.width - 2 * inset)
        inner_h = max(0, self.height - 2 * inset)
        line_h = gfx.line_height(self.text, font)
        _, glyph_h = gfx.get_text_size(self.text, font)
        # Cap how many lines we'll ever draw to however many actually fit
        # in the box's own height, on top of (not instead of) max_lines --
        # a box sized smaller than max_lines*line_h would otherwise draw
        # ink past self.height, escaping this widget's (and its parent
        # panel's) bounds instead of just truncating harder.
        #
        # Mirrors measure()'s own content_h formula, (n-1)*line_h+glyph_h,
        # rather than a flat inner_h // line_h -- line_h already carries a
        # trailing 1px inter-line gap that only applies BETWEEN rows, not
        # after the last one (see display_gfx.line_height's docstring), so
        # a box measure() sized for exactly 1 line has inner_h == glyph_h,
        # strictly less than line_h -- inner_h // line_h would floor that
        # to 0 fitting lines and silently draw nothing.
        fits = 1 + (inner_h - glyph_h) // line_h if line_h > 0 and inner_h >= glyph_h else 0
        limit = fits if self.max_lines is None else min(self.max_lines, fits)
        for row, line in enumerate(self._wrap(inner_w, max_lines=limit)):
            gfx.draw_text(self._clip_to_width(line, inner_w, font), inner_x, inner_y + row * line_h, font=font)

        # inverted and border both draw AT self.bounds (post-margin),
        # not the padded inner rect -- same ordering as layout._Stack:
        # invert whatever was actually drawn (turns white-on-black ink
        # into black-on-white automatically, no child/text awareness
        # needed), then draw the border on top so it stays a crisp
        # frame instead of getting flipped into invisible-against-itself.
        if self.inverted:
            gfx.invert_area(self.x, self.y, self.width, self.height)
        if self.border > 0:
            self._draw_border()

    def _draw_border(self) -> None:
        b = self.border
        x, y, w, h = self.x, self.y, self.width, self.height
        fill = 0 if self.inverted else 255
        self._gfx.draw_area(x, y, w, b, fill=fill)
        self._gfx.draw_area(x, y + h - b, w, b, fill=fill)
        self._gfx.draw_area(x, y, b, h, fill=fill)
        self._gfx.draw_area(x + w - b, y, b, h, fill=fill)
        # See Menu._draw_border -- chamfer the 4 outer corner pixels back
        # to background so the frame doesn't read as a harsh square box.
        bg = 255 - fill
        self._gfx.draw_area(x, y, 1, 1, fill=bg)
        self._gfx.draw_area(x + w - 1, y, 1, 1, fill=bg)
        self._gfx.draw_area(x, y + h - 1, 1, 1, fill=bg)
        self._gfx.draw_area(x + w - 1, y + h - 1, 1, 1, fill=bg)

    def handle_key(self, keycode: str) -> bool:
        return False


class Screen:
    """The common 'title + wrapped body text' pattern (V1's set_screen).
    Shares Toast's wrap-and-position logic rather than duplicating it."""

    def __init__(self, gfx, title: str, body: str) -> None:
        self._toast = Toast(gfx)
        self.title = title
        self.body = body

    def draw(self) -> None:
        self._toast._render(self.title, self.body)


class TabView:
    """Shared paged-content frame with a centered title, small left/right
    arrows, and directional horizontal page transitions.

    Each page spec is a dict with:
      - title: header text for that page
      - build: zero-arg callable returning the page widget

    LEFT/RIGHT (and A/D) switch pages; all other keys are forwarded to the
    current page widget's handle_key(), if it exposes one. The owning app is
    responsible for calling tick(dt) once per frame so both the page slide and
    the hosted widget's own animation (e.g. Menu highlight glide) can advance.
    """

    _ARROW_GUTTER = 8
    _HEADER_GAP = 2
    _SNAPSHOT_BLEED = 3

    class _PageShell:
        def __init__(self, gfx, child) -> None:
            self._gfx = gfx
            self.child = child
            self.bounds = Box()

        @property
        def x(self) -> int:
            return self.bounds.x

        @property
        def y(self) -> int:
            return self.bounds.y

        @property
        def width(self) -> int:
            return self.bounds.width

        @property
        def height(self) -> int:
            return self.bounds.height

        def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
            self.bounds = Box(x, y, width, height)
            self.child.set_bounds(x, y, width, height)

        def animation_bounds(self) -> Tuple[int, int, int, int]:
            child_bounds = getattr(self.child, "animation_bounds", None)
            if callable(child_bounds):
                return child_bounds()
            return self.bounds.as_tuple()

        def draw(self) -> None:
            x, y, width, height = self.animation_bounds()
            self._gfx.clear_area(x, y, width, height)
            invalidate = getattr(self.child, "invalidate_draw_cache", None)
            if invalidate is not None:
                invalidate()
            self.child.draw()

        def handle_key(self, keycode: str) -> bool:
            handler = getattr(self.child, "handle_key", None)
            return bool(handler(keycode)) if handler else False

        def tick(self, dt: float) -> None:
            tick = getattr(self.child, "tick", None)
            if tick is not None:
                tick(dt)

    class _SnapshotSurface:
        def __init__(self, gfx, image, x: int, y: int, width: int, height: int) -> None:
            self._gfx = gfx
            self._image = image
            self.bounds = Box(x, y, width, height)

        @property
        def x(self) -> int:
            return self.bounds.x

        @property
        def y(self) -> int:
            return self.bounds.y

        @property
        def width(self) -> int:
            return self.bounds.width

        @property
        def height(self) -> int:
            return self.bounds.height

        def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
            self.bounds = Box(x, y, width, height)

        def animation_bounds(self) -> Tuple[int, int, int, int]:
            return self.bounds.as_tuple()

        def draw(self) -> None:
            self._gfx.draw_image(self._image, self.x, self.y)

    class _SurfaceSlide:
        def __init__(self, animation, widget, from_x: int, duration: float, easing: str) -> None:
            self._widget = widget
            self._target_x = widget.x
            self._tween = animation.make_tween(float(from_x), float(self._target_x), duration=duration, easing=easing)
            widget.set_bounds(from_x, widget.y, widget.width, widget.height)

        @property
        def done(self) -> bool:
            return self._tween.done

        def finish(self) -> None:
            if not self._tween.done:
                self.update(self._tween.duration)

        def update(self, dt: float) -> None:
            if self._tween.done:
                return
            self._tween.update(dt)
            self._widget.set_bounds(int(round(self._tween.value)), self._widget.y, self._widget.width, self._widget.height)

    def __init__(
        self,
        gfx,
        animation,
        pages: List[Dict[str, Any]],
        initial_index: int = 0,
        font=None,
        duration: float = 0.15,
        easing: str = "ease_out_back",
    ) -> None:
        if not pages:
            raise ValueError("TabView requires at least one page")
        self._gfx = gfx
        self._animation = animation
        self._pages = [self._normalize_page(page) for page in pages]
        self._font = font or gfx.fonts["small"]
        self._duration = duration
        self._easing = easing
        self.bounds = Box()
        self.current_index = max(0, min(initial_index, len(self._pages) - 1))
        self._current_page = self._build_page(self.current_index)
        self._incoming_surface = None
        self._outgoing_surface = None
        self._incoming_anim = None
        self._outgoing_anim = None
        self._queued_direction = None

    @staticmethod
    def _normalize_page(page: Dict[str, Any]) -> Dict[str, Any]:
        title = page.get("title", "") if isinstance(page, dict) else ""
        build = page.get("build") if isinstance(page, dict) else None
        if not callable(build):
            raise ValueError("TabView pages must provide a callable 'build'")
        return {"title": title, "build": build}

    @property
    def current_widget(self):
        return self._current_page.child

    def _build_page(self, index: int):
        return self._PageShell(self._gfx, self._pages[index]["build"]())

    def _make_slide(self, widget, from_x: int):
        return self._SurfaceSlide(
            self._animation,
            widget,
            from_x=from_x,
            duration=self._duration,
            easing=self._easing,
        )

    def _capture_page_snapshot(self, page, x: int, y: int, width: int, height: int):
        # Some child widgets can draw a couple of pixels past their nominal
        # content bounds (e.g. glyph bearings / highlight halos). Capture,
        # clear, and restore with a small bleed so that off-rect ink does not
        # leak into the arrow gutters during tab snapshot generation.
        bleed = self._SNAPSHOT_BLEED
        clear_x0 = max(self.x, x - bleed)
        clear_y0 = max(self.y, y - bleed)
        clear_x1 = min(self.x + self.width, x + width + bleed)
        clear_y1 = min(self.y + self.height, y + height + bleed)
        clear_w = max(0, clear_x1 - clear_x0)
        clear_h = max(0, clear_y1 - clear_y0)

        previous = self._gfx.capture_area(clear_x0, clear_y0, clear_w, clear_h)
        self._gfx.begin_batch()
        self._gfx.clear_area(clear_x0, clear_y0, clear_w, clear_h)
        page.draw()
        snapshot = self._gfx.capture_area(x, y, width, height)
        self._gfx.draw_image(previous, clear_x0, clear_y0)
        self._gfx.end_batch()
        return snapshot

    def _page_title(self) -> str:
        return str(self._pages[self.current_index]["title"])

    def _header_height(self) -> int:
        return self._gfx.get_text_size("Ag", self._font)[1]

    def _content_rect(self) -> Tuple[int, int, int, int]:
        header_height = self._header_height()
        content_y = self.y + header_height + self._HEADER_GAP
        content_height = max(0, self.height - header_height - self._HEADER_GAP)
        content_x = self.x + self._ARROW_GUTTER
        content_width = max(0, self.width - 2 * self._ARROW_GUTTER)
        return (content_x, content_y, content_width, content_height)

    def _set_page_bounds(self, widget, x: int, y: int, width: int, height: int) -> None:
        if widget is None:
            return
        widget.set_bounds(x, y, width, height)

    def _transition_active(self) -> bool:
        return self._outgoing_anim is not None or self._incoming_anim is not None

    def _clip_title(self, text: str, width: int) -> str:
        """Character-truncate `text` (with a trailing "...") if it's wider
        than `width` -- mirrors Menu._clip_label. An unclipped title drawn
        past _draw_header's own clear_area(self.x, self.y, self.width, ...)
        rect never gets erased on a later redraw with a shorter title
        (nothing else owns that strip), leaving a permanent ghost sliver at
        the tab's edge."""
        if width <= 0:
            return ""
        if self._gfx.get_text_size(text, self._font)[0] <= width:
            return text
        while text and self._gfx.get_text_size(text + "...", self._font)[0] > width:
            text = text[:-1]
        return f"{text}..." if text else ""

    def _draw_header(self) -> None:
        title = self._clip_title(self._page_title(), self.width)
        title_width, title_height = self._gfx.get_text_size(title, self._font)
        title_x = self.x + max(0, (self.width - title_width) // 2)
        self._gfx.clear_area(self.x, self.y, self.width, self._header_height())
        self._gfx.draw_text(title, title_x, self.y, self._font)

    def _draw_arrows(self) -> None:
        _, content_y, _, content_height = self._content_rect()
        arrow_height = self._gfx.get_text_size("<", self._font)[1]
        arrow_y = content_y + max(0, (content_height - arrow_height) // 2)
        self._gfx.clear_area(self.x, content_y, self._ARROW_GUTTER, content_height)
        self._gfx.clear_area(self.x + self.width - self._ARROW_GUTTER, content_y, self._ARROW_GUTTER, content_height)
        if self.current_index > 0:
            self._gfx.draw_text("<", self.x + 1, arrow_y, self._font)
        if self.current_index < len(self._pages) - 1:
            right_x = self.x + self.width - self._ARROW_GUTTER + 1
            self._gfx.draw_text(">", right_x, arrow_y, self._font)

    def _draw_chrome(self) -> None:
        self._draw_header()
        self._draw_arrows()

    def measure(self, available_w: int, available_h: int) -> Tuple[int, int]:
        return (available_w, available_h)

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        self.bounds = Box(x, y, width, height)
        content_x, content_y, content_width, content_height = self._content_rect()
        self._set_page_bounds(self._current_page, content_x, content_y, content_width, content_height)
        self._set_page_bounds(self._incoming_surface, content_x, content_y, content_width, content_height)
        self._set_page_bounds(self._outgoing_surface, content_x, content_y, content_width, content_height)

    @property
    def x(self) -> int:
        return self.bounds.x

    @x.setter
    def x(self, value: int) -> None:
        self.bounds.x = value

    @property
    def y(self) -> int:
        return self.bounds.y

    @y.setter
    def y(self, value: int) -> None:
        self.bounds.y = value

    @property
    def width(self) -> int:
        return self.bounds.width

    @property
    def height(self) -> int:
        return self.bounds.height

    def draw(self) -> None:
        self._gfx.clear_area(self.x, self.y, self.width, self.height)
        self._gfx.clear_area(*self._content_rect())
        if self._outgoing_surface is not None:
            self._outgoing_surface.draw()
        if self._incoming_surface is not None:
            self._incoming_surface.draw()
        elif self._current_page is not None:
            self._current_page.draw()
        self._draw_chrome()

    def _finish_anim(self, anim) -> None:
        if anim is not None and not anim.done:
            anim.finish()

    def _settle_transition(self) -> None:
        self._finish_anim(self._outgoing_anim)
        self._finish_anim(self._incoming_anim)
        self._outgoing_anim = None
        self._incoming_anim = None
        self._outgoing_surface = None
        self._incoming_surface = None
        self._queued_direction = None
        self.draw()

    def switch(self, direction: int) -> bool:
        new_index = self.current_index + direction
        if not (0 <= new_index < len(self._pages)):
            return False

        if self._transition_active():
            self._queued_direction = direction
            return True

        content_x, content_y, content_width, content_height = self._content_rect()
        old_snapshot = self._gfx.capture_area(content_x, content_y, content_width, content_height)
        new_page = self._build_page(new_index)
        self._set_page_bounds(new_page, content_x, content_y, content_width, content_height)
        new_snapshot = self._capture_page_snapshot(new_page, content_x, content_y, content_width, content_height)
        self.current_index = new_index
        self._current_page = new_page
        self._outgoing_surface = self._SnapshotSurface(
            self._gfx, old_snapshot, content_x, content_y, content_width, content_height
        )
        self._incoming_surface = self._SnapshotSurface(
            self._gfx, new_snapshot, content_x, content_y, content_width, content_height
        )

        exit_x = content_x - content_width if direction > 0 else content_x + content_width
        self._outgoing_surface.set_bounds(exit_x, content_y, content_width, content_height)
        self._outgoing_anim = self._make_slide(self._outgoing_surface, from_x=content_x)

        enter_x = content_x + content_width if direction > 0 else content_x - content_width
        self._incoming_anim = self._make_slide(self._incoming_surface, from_x=enter_x)
        self._draw_chrome()
        return True

    def handle_key(self, keycode: str) -> bool:
        if keycode in ("KEY_LEFT", "KEY_A"):
            return self.switch(-1) or True
        if keycode in ("KEY_RIGHT", "KEY_D"):
            return self.switch(1) or True
        handler = getattr(self._current_page, "handle_key", None)
        return bool(handler(keycode)) if handler else False

    def tick(self, dt: float) -> None:
        had_transition = self._transition_active()
        moved = False
        if self._outgoing_anim is not None:
            self._outgoing_anim.update(dt)
            moved = True
            if self._outgoing_anim.done:
                self._outgoing_anim = None
        if self._incoming_anim is not None:
            self._incoming_anim.update(dt)
            moved = True
            if self._incoming_anim.done:
                self._incoming_anim = None

        if had_transition and not self._transition_active():
            self._outgoing_surface = None
            self._incoming_surface = None
            self.draw()

        if had_transition and not self._transition_active() and self._queued_direction is not None:
            direction = self._queued_direction
            self._queued_direction = None
            self.switch(direction)
            return

        if not had_transition and not moved and self._current_page is not None:
            self._current_page.tick(dt)

        if moved:
            self.draw()


class UIPackage(Package):
    package_id = "ui"
    display_name = "UI Widgets"
    priority = 60
    capability_tags = {"widgets"}
    package_requires = {"display_gfx", "animation", "images"}

    def initialize(self) -> None:
        self._gfx = self.require("display_gfx")
        self._anim = self.require("animation")
        self._images = self.require("images")

    def make_menu(
        self, items, x=0, y=0, width=None, height=None, on_select=None, on_change=None,
        padding=2, margin=0, border=0, inverted=False, selected_padding=None, spacing=0,
        highlight_easing="ease_in_out", highlight_settle_easing=None, highlight_duration=None,
    ) -> Menu:
        """Scrollable, keyboard-navigable list of MenuItems. on_select(value)
        fires on Enter, on_change(value) fires whenever the highlighted item
        changes (e.g. on UP/DOWN). width/height default to filling the
        display from (x, y). selected_padding is the halo gap between the
        selection highlight background and the row's text (distinct from
        `padding`, which insets the Menu's own content from its box edges).
        spacing is the gap BETWEEN rows (distinct from both -- same n-1-gaps
        convention as Row/Column's `spacing`), added between rows without
        changing each row's own height or halo sizing. selected_padding
        defaults to Menu.SELECTED_HALO_PADDING. highlight_easing/
        highlight_duration pick the curve and time the highlight glides/
        resizes along between rows (see animation.EASINGS) — duration
        defaults to Menu._HIGHLIGHT_DURATION. highlight_settle_easing, if
        given, is used instead of highlight_easing whenever a move starts
        from a full stop (no previous highlight tween still in flight) —
        e.g. an overshoot curve that should only play once navigation
        actually settles, not on every hop while rapidly scrolling."""
        display = self.resources.core.display
        w = width if width is not None else display.width
        h = height if height is not None else display.height - y
        return Menu(
            self._gfx, items, x=x, y=y, width=w, height=h, on_select=on_select, on_change=on_change,
            padding=padding, margin=margin, border=border, inverted=inverted,
            selected_padding=selected_padding, spacing=spacing, highlight_easing=highlight_easing,
            highlight_settle_easing=highlight_settle_easing,
            highlight_duration=highlight_duration, tween_factory=self._anim.make_tween,
        )

    def make_text_field(self, text_input, x=0, y=0, width=None, font=None, display_transform=None, valign="start") -> TextField:
        """Single-line editable text widget wrapping a `text_input` (see
        context["input"]["make_text_input"]) — handle_key() feeds keys to
        it, .tick() drives cursor blink/IME state. display_transform, if
        given, maps the raw buffer to what's actually drawn (e.g. masking
        a password field) without altering the underlying text."""
        display = self.resources.core.display
        w = width if width is not None else display.width - x
        return TextField(
            self._gfx,
            text_input,
            x=x,
            y=y,
            width=w,
            font=font,
            display_transform=display_transform,
            valign=valign,
        )

    def make_dialog(self, title, message, on_yes=None, on_no=None) -> Dialog:
        """Modal yes/no confirmation box, centered on screen. Feed it every
        keycode via handle_key(); on_yes()/on_no() fire once the user picks
        (Enter/Y or ESC/N)."""
        return Dialog.confirm(self._gfx, title, message, on_yes, on_no)

    def make_progress_bar(
        self, x=0, y=0, width=0, height=4, font=None, label=None, show_percent=False, value_text=None
    ) -> ProgressBar:
        """Horizontal fill bar. Drive it with set_progress(0.0-1.0); label is
        drawn to its left. show_percent=True auto-renders "NN%" as the value
        text, or call set_value_text() for custom text (e.g. "3/10")."""
        return ProgressBar(
            self._gfx, x, y, width, height, font=font,
            label=label, show_percent=show_percent, value_text=value_text,
        )

    def make_toast(self) -> Toast:
        """Transient overlay notification. Call .loading(text)/.message(title,
        body)/.error(text) to show one; each replaces whatever's currently
        showing."""
        return Toast(self._gfx)

    def make_scroll_panel(self, x=0, y=0, width=128, height=64, text="") -> ScrollPanel:
        """Word-wrapped block of `text` that scrolls one line at a time via
        handle_key() on UP/DOWN (and W/S)."""
        return ScrollPanel(self._gfx, x, y, width, height, text=text)

    def make_text_box(
        self, text="", font=None, max_lines=None, padding=0, margin=0, border=0, inverted=False, fill=False
    ) -> TextBox:
        """Static (non-scrolling) word-wrapped text block, truncated to
        max_lines if given. Unlike ScrollPanel this has no scroll/key
        handling — use it for labels/descriptions that don't need to move."""
        return TextBox(
            self._gfx,
            text=text,
            font=font,
            max_lines=max_lines,
            padding=padding,
            margin=margin,
            border=border,
            inverted=inverted,
            fill=fill,
        )

    def make_screen(self, title, body) -> Screen:
        """Static title + body layout, drawn once via .draw() (no key
        handling of its own — pair with a Menu/TextField for interaction)."""
        return Screen(self._gfx, title, body)

    def make_tab_view(self, pages, initial_index=0, font=None, duration=0.15, easing="ease_out_back") -> TabView:
        """Paged content frame with a centered title, arrow affordances, and
        horizontal LEFT/RIGHT transitions between page widgets."""
        return TabView(
            self._gfx,
            self._anim,
            pages,
            initial_index=initial_index,
            font=font,
            duration=duration,
            easing=easing,
        )

    def make_label(self, text="", font=None, fill=255, align="start") -> Label:
        """Single line of text as a layout leaf node (see layout.py) — use
        inside a Row/Column tagged content()/fill(); measures itself
        against whatever font is currently active."""
        return Label(self._gfx, text=text, font=font, fill=fill, align=align)

    def make_image(self, path, size=None, loop=True, allow_upscale=None) -> Image:
        """Static image or animated GIF as a layout leaf node (auto-detected
        from the path extension). size=None keeps natural size, size="fill"
        scales to fill its box preserving aspect ratio, a fixed int forces a
        size x size box. Call .update(dt) each frame to tick GIF playback."""
        return Image(self._images, self._gfx, path, size=size, loop=loop, allow_upscale=allow_upscale)

    def make_row(
        self, children=None, padding=0, margin=0, spacing=0, inverted=False, fill=False, border=0,
        scroll=False, scroll_snap=True, scroll_step=4,
    ) -> Row:
        """Horizontal layout container — children stack left to right. See
        layout.py's _Stack docstring for the padding/margin/spacing/border/
        fill/scroll box model; `children` is a list of (node, size) tuples
        where size is layout.FILL, layout.CONTENT, or a fixed pixel int."""
        return Row(
            children=children,
            padding=padding,
            margin=margin,
            spacing=spacing,
            gfx=self._gfx,
            inverted=inverted,
            fill=fill,
            border=border,
            scroll=scroll,
            scroll_snap=scroll_snap,
            scroll_step=scroll_step,
        )

    def make_column(
        self, children=None, padding=0, margin=0, spacing=0, inverted=False, fill=False, border=0,
        scroll=False, scroll_snap=True, scroll_step=4,
    ) -> Column:
        """Vertical layout container — children stack top to bottom. Same
        knobs/semantics as make_row(), just the other main axis."""
        return Column(
            children=children,
            padding=padding,
            margin=margin,
            spacing=spacing,
            gfx=self._gfx,
            inverted=inverted,
            fill=fill,
            border=border,
            scroll=scroll,
            scroll_snap=scroll_snap,
            scroll_step=scroll_step,
        )

    def layout_root(
        self, node, x=None, y=None, width=None, height=None, padding: int = 0, margin: int = 0
    ) -> None:
        """Convenience: run a layout pass over `node` covering the full
        display (or an explicit rect), then draw it. Call again — e.g.
        after a language toggle changes font metrics, or content changes
        enough to need a reflow — to relayout from scratch.

        padding/margin follow the same CSS box model Row/Column use (see
        layout._Stack's docstring): margin insets `node`'s own bounds from
        the display edge, padding then insets where `node` itself draws
        from THAT. Both are here so a non-container root (a single Label
        or widget) can get either without being wrapped in a Column purely
        for that. There's no `spacing` here — that's the gap between a
        Row/Column's several children, and layout_root only ever has the
        one root node.

        Clears the whole (un-inset) region FIRST, before any child draws.
        Apps typically rebuild a fresh widget tree on a full relayout (e.g.
        Proxi constructs a new title Label each time _render_ready() runs)
        rather than reusing the previous instances, so no individual widget
        has any memory of where its PREVIOUS incarnation drew — if row
        sizes shift (e.g. a language swap changes the title's measured
        height, pushing everything below it up or down), the strip between
        a sibling's old and new position would otherwise never get
        cleared, since each widget only clears its own current bounds."""
        display = self.resources.core.display
        x = 0 if x is None else x
        y = 0 if y is None else y
        width = display.width if width is None else width
        height = display.height if height is None else height
        self._gfx.clear_area(x, y, width, height)
        x += margin
        y += margin
        width = max(0, width - 2 * margin)
        height = max(0, height - 2 * margin)
        x += padding
        y += padding
        width = max(0, width - 2 * padding)
        height = max(0, height - 2 * padding)
        node.set_bounds(x, y, width, height)
        node.draw()

    def get_public_api(self) -> Dict[str, Any]:
        # Every key here is the snake_case name of the factory it points to
        # (make_menu -> "menu", etc.), matching every other package's
        # get_public_api() convention — see STYLE_GUIDE.md's "UI widgets"
        # section. menu_item is the one entry that isn't a factory (MenuItem
        # is a plain data holder that doesn't need `gfx` injected), but it
        # keeps the same snake_case key shape as everything else here.
        return {
            "menu": self.make_menu,
            "menu_item": MenuItem,
            "text_field": self.make_text_field,
            "dialog": self.make_dialog,
            "progress_bar": self.make_progress_bar,
            "toast": self.make_toast,
            "scroll_panel": self.make_scroll_panel,
            "text_box": self.make_text_box,
            "screen": self.make_screen,
            "tab_view": self.make_tab_view,
            # Layout primitives — compose the widgets above without hardcoded
            # pixel positions; see core_os/packages/ui/layout.py.
            "label": self.make_label,
            "image": self.make_image,
            "row": self.make_row,
            "column": self.make_column,
            "layout_root": self.layout_root,
            # fill(widget)/content(widget) -> (widget, FILL)/(widget, CONTENT),
            # so callers building a Row/Column's children list don't hand-write
            # that tuple themselves. A fixed pixel size still just goes
            # straight in as (widget, 24) -- no helper needed for that case.
            "fill": _fill,
            "content": _content,
        }


AVAILABLE_PACKAGES = [UIPackage]
