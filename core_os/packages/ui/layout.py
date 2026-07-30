"""Layout primitives — Row/Column containers that position child widgets
automatically based on declared sizing rules (FILL / CONTENT / a fixed
pixel count), instead of every widget or app hardcoding x/y/width/height.

This is what makes the UI adapt when the rendered text changes metrics
(e.g. misaki_gothic.ttf's kana glyphs measuring a pixel taller than Latin
ones — see display_gfx.Package.line_height): CONTENT-sized nodes measure
themselves against whatever font is *currently* active every time layout
runs, so a Column re-flows correctly instead of leaving stale pixel
offsets tuned for one script's metrics.

Layout is not cached — call .set_bounds(x, y, w, h) again (a "relayout")
any time something that affects measurement changes: the screen was
resized, content changed, or — most commonly here — the language toggled
and font metrics changed with it.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple, Union

FILL = "fill"        # take an equal share of whatever main-axis space is left over
CONTENT = "content"  # take exactly this node's measured intrinsic size
SizeSpec = Union[str, int]  # FILL, CONTENT, or a fixed pixel count


class Box:
    """A node's current on-screen rectangle."""

    __slots__ = ("x", "y", "width", "height")

    def __init__(self, x: int = 0, y: int = 0, width: int = 0, height: int = 0) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)


class LayoutNode:
    """Base class every layout-participating widget/container can inherit
    (existing widgets like Menu/TextField/ScrollPanel duck-type this
    instead — see package.py — so this base is mainly documentation of the
    contract, plus a ready-made no-op for simple leaf nodes)."""

    def __init__(self) -> None:
        self.bounds = Box()

    def measure(self, available_w: int, available_h: int) -> Tuple[int, int]:
        """Preferred (width, height) within at most this much space. Called
        by a parent Container BEFORE set_bounds() to size CONTENT children."""
        return (0, 0)

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        """Assign the final pixel rect. Does NOT draw — call .draw()
        separately once the whole tree has its bounds assigned."""
        self.bounds = Box(x, y, width, height)

    def draw(self) -> None:
        pass

    def handle_key(self, keycode: str) -> bool:
        return False

    # Plain .x/.y/.width/.height proxying self.bounds -- see _Stack's
    # identical properties for why: every ui widget needs to share this same
    # shape so generic movement helpers (animation.doslide) work uniformly.
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


def _measure(node, w: int, h: int) -> Tuple[int, int]:
    fn = getattr(node, "measure", None)
    return fn(w, h) if fn else (0, 0)


def _set_bounds(node, x: int, y: int, w: int, h: int) -> None:
    fn = getattr(node, "set_bounds", None)
    if fn:
        fn(x, y, w, h)


def _draw(node) -> None:
    fn = getattr(node, "draw", None)
    if fn:
        fn()


def _handle_key(node, keycode: str) -> bool:
    fn = getattr(node, "handle_key", None)
    return bool(fn(keycode)) if fn else False


def scrollbar_thumb(viewport: int, content: int, start: int, visible: int) -> Tuple[int, int]:
    """Proportional scrollbar thumb (position, size) in pixels along the
    scroll axis, given the viewport size, total scrollable content size, and
    the pixel span of what's currently visible starting at `start`. Shared by
    _Stack's `scroll=True` containers and ScrollPanel (built on top of one)
    so this math lives in exactly one place rather than being re-derived per
    scrollable widget."""
    if content <= 0 or content <= visible:
        return (0, viewport)
    size = max(1, viewport * visible // content)
    remaining = content - visible
    pos = (start * (viewport - size)) // remaining
    return (pos, size)


class _Stack:
    """Shared implementation for Row/Column. main_axis: 1 = vertical
    (Column, stacks top-to-bottom), 0 = horizontal (Row, left-to-right).

    Three knobs, matching the CSS box model plus flex/grid `gap`:
      - margin:  moves the BOUNDS in. self.bounds (this box's own rect,
        what a parent sees and what e.g. clear_area/invert_area key off)
        shrinks to leave an empty gap around the whole box, the same way a
        CSS margin carves out space between an element and its siblings/
        container edge rather than being part of the element itself.
      - padding: moves the CONTENT in. Insets where children are laid out
        from this box's own (already margined, and border-inset if
        `border` is set) bounds — CSS padding, between the border and the
        content.
      - spacing: the gap BETWEEN children (n-1 gaps for n children, none
        before the first or after the last) — CSS flex/grid `gap`, a
        distinct third concept from either margin or padding.

    inverted and border are the two other visual knobs, both opt-in and
    both requiring `gfx` — the raw display_gfx Package instance (the same
    object Label is constructed with, method-call style: gfx.draw_area(...),
    NOT the dict apps get via context["display_gfx"]) — since drawing them
    needs direct pixel access this class doesn't otherwise depend on:
      - border: an N-pixel white outline drawn at self.bounds' edge (i.e.
        outside padding, inside margin — same position CSS border sits).
        Also insets where padding starts from, the same way a real border
        occupies space rather than overlapping the content.
      - inverted: after children draw themselves normally (whatever ink
        color they each individually chose, typically white on the
        default black canvas), the container's own bounds get pixel-
        inverted (see gfx.invert_area) — flipping that into black ink on a
        white background regardless of what was actually drawn, so no
        child needs to know or care that it's sitting inside an inverted
        box. The border (if any) is drawn AFTER inverting, in the
        opposite of the fill color, so it stays a crisp visible frame
        instead of getting inverted into invisible-against-itself.
      - fill: paints self.bounds solid black BEFORE children draw — an
        explicit background, distinct from `inverted` (which flips
        whatever children already drew rather than laying down a color
        first). Mainly useful sitting inside an `inverted` (white-
        background) ancestor, so one nested box can still punch back to a
        black background of its own without the child widgets needing to
        know or care that they're inside an inverted box.

    `scroll` is a fourth, orthogonal knob: when True, children keep their own
    intrinsic (CONTENT) main-axis size regardless of the `size` tag they were
    added with (FILL doesn't mean anything once content can exceed the
    viewport). KEY_UP/KEY_DOWN (and W/S) move the visible window. A 1px
    gutter is always reserved on the trailing cross-axis edge for a
    scrollbar thumb (see scrollbar_thumb) whenever content overflows. This
    is the primitive ScrollPanel is built from (see package.py) -- scrolling
    is a Row/Column option, not a separate bespoke widget.

    `scroll_snap` picks how that window moves:
      - True (default): only however many children fully fit the viewport
        at a time are laid out/drawn, and a key press moves the window one
        WHOLE child at a time (same granularity Menu/ScrollPanel already
        use) -- simple, and needs no real pixel-clipping since a child is
        never drawn anywhere it'd overflow this container's own bounds.
      - False: the window moves by `scroll_step` pixels per key press, and
        children can end up PARTIALLY visible at either edge. Since gfx has
        no clip-region primitive, a partially-visible child still draws its
        whole self (potentially overflowing this container's bounds) --
        _draw_clipped_child then erases just the overflow by capturing the
        strip beyond this container's edge with gfx.capture_area() before
        the child draws and pasting it straight back after, restoring
        whatever was legitimately there (a sibling, empty padding) instead
        of leaving the child's ink stuck outside this container's box.
    """

    main_axis: int = 1

    def __init__(
        self,
        children: Optional[List[Tuple[object, SizeSpec]]] = None,
        padding: int = 0,
        margin: int = 0,
        spacing: int = 0,
        gfx=None,
        inverted: bool = False,
        fill: bool = False,
        border: int = 0,
        scroll: bool = False,
        scroll_snap: bool = True,
        scroll_step: int = 4,
    ) -> None:
        self.children: List[Tuple[object, SizeSpec]] = list(children or [])
        self.padding = padding
        self.margin = margin
        self.spacing = spacing
        self._gfx = gfx
        self.inverted = inverted
        self.fill = fill
        self.border = border
        self.scroll_snap = scroll_snap
        self.scroll_step = scroll_step
        self.scroll = scroll
        self.bounds = Box()
        self._scroll_index = 0
        self._scroll_max_index = 0
        self._scroll_window = (0, 0)
        self._scroll_offset_px = 0
        self._scroll_max_offset_px = 0
        self._scroll_visible_indices: List[int] = []
        self._scroll_inner = (0, 0, 0, 0)
        self._scroll_metrics = (0, 0, 0, 0)  # (content_px, start_px, visible_px, viewport_px)

    def add(self, node, size: SizeSpec = CONTENT):
        self.children.append((node, size))
        return node

    # Plain .x/.y/.width/.height proxying self.bounds -- Menu/TextField/
    # ScrollPanel/TextBox all expose these as plain attributes (they predate
    # the Row/Column/Label split into a separate self.bounds object), and
    # anything generic that moves a widget around (e.g. animation.doslide,
    # which reads/writes .x/.y directly) needs every ui widget to share that
    # same shape rather than special-casing which ones only have .bounds.
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

    def measure(self, available_w: int, available_h: int) -> Tuple[int, int]:
        content_inset = self.padding + self.border
        inner_w = max(0, available_w - 2 * (self.margin + content_inset))
        inner_h = max(0, available_h - 2 * (self.margin + content_inset))
        if self.scroll:
            if self.main_axis == 1:
                inner_w = max(0, inner_w - 1)
            else:
                inner_h = max(0, inner_h - 1)
        main_total = 0
        cross_max = 0
        for i, (child, size) in enumerate(self.children):
            cw, ch = _measure(child, inner_w, inner_h)
            main = ch if self.main_axis == 1 else cw
            cross = cw if self.main_axis == 1 else ch
            main_total += main + (self.spacing if i > 0 else 0)
            cross_max = max(cross_max, cross)
        inset = 2 * (self.margin + content_inset)
        gutter = 1 if self.scroll else 0
        if self.main_axis == 1:
            return (cross_max + inset + gutter, main_total + inset)
        return (main_total + inset, cross_max + inset + gutter)

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        # Margin first: self.bounds reflects the margined-in rect, not the
        # raw space the parent handed us. border+padding then further
        # inset where children actually get laid out, without changing
        # self.bounds itself (border/inverted draw AT self.bounds).
        x += self.margin
        y += self.margin
        width = max(0, width - 2 * self.margin)
        height = max(0, height - 2 * self.margin)
        self.bounds = Box(x, y, width, height)

        content_inset = self.border + self.padding
        inner_x = x + content_inset
        inner_y = y + content_inset
        inner_w = max(0, width - 2 * content_inset)
        inner_h = max(0, height - 2 * content_inset)

        if self.scroll:
            if self.main_axis == 1:
                inner_w = max(0, inner_w - 1)
            else:
                inner_h = max(0, inner_h - 1)
            self._layout_scroll(inner_x, inner_y, inner_w, inner_h)
            return

        main_space = inner_h if self.main_axis == 1 else inner_w

        # Pass 1: resolve CONTENT/fixed sizes, tally how many FILL slots
        # want a share of whatever's left.
        sizes: List[int] = [0] * len(self.children)
        fill_indices: List[int] = []
        used = self.spacing * max(0, len(self.children) - 1)
        for i, (child, size) in enumerate(self.children):
            if size == FILL:
                fill_indices.append(i)
                continue
            if size == CONTENT:
                cw, ch = _measure(child, inner_w, inner_h)
                sizes[i] = ch if self.main_axis == 1 else cw
            else:
                sizes[i] = int(size)
            used += sizes[i]

        remaining = max(0, main_space - used)
        if fill_indices:
            share = remaining // len(fill_indices)
            extra = remaining - share * len(fill_indices)
            for j, i in enumerate(fill_indices):
                sizes[i] = share + (extra if j == len(fill_indices) - 1 else 0)

        # Pass 2: assign bounds. Cross-axis gets the full inner width/height
        # — a child that wants to align itself within that (e.g. centered
        # text) can do so using its own measured size, since it still
        # knows what it asked for via measure().
        cursor = inner_y if self.main_axis == 1 else inner_x
        for i, (child, _size) in enumerate(self.children):
            if self.main_axis == 1:
                _set_bounds(child, inner_x, cursor, inner_w, sizes[i])
            else:
                _set_bounds(child, cursor, inner_y, sizes[i], inner_h)
            cursor += sizes[i] + self.spacing

    def _visible_children(self) -> List[Tuple[object, SizeSpec]]:
        if not self.scroll:
            return self.children
        if self.scroll_snap:
            start, count = self._scroll_window
            return self.children[start:start + count]
        return [self.children[i] for i in self._scroll_visible_indices]

    def draw(self) -> None:
        if self.scroll:
            # Unlike the non-scroll case (where every child fully repaints
            # its own bounds every frame, covering the whole main_space
            # between them), a scrolled window's total visible content can
            # be SHORTER than the viewport (e.g. scrolled to the last few
            # children with nothing to fill the rest) -- clearing the whole
            # viewport first avoids leaving a previous frame's child ink in
            # that leftover strip.
            self._gfx.clear_area(self.bounds.x, self.bounds.y, self.bounds.width, self.bounds.height)
        if self.fill and self._gfx is not None:
            self._gfx.draw_area(self.bounds.x, self.bounds.y, self.bounds.width, self.bounds.height, fill=0)
        for child, _size in self._visible_children():
            if self.scroll and not self.scroll_snap:
                self._draw_clipped_child(child)
            else:
                _draw(child)
        if self.inverted and self._gfx is not None:
            self._gfx.invert_area(self.bounds.x, self.bounds.y, self.bounds.width, self.bounds.height)
        if self.border > 0 and self._gfx is not None:
            self._draw_border()
        if self.scroll:
            self._draw_scrollbar()

    def _draw_clipped_child(self, child) -> None:
        """Draw `child` (which may extend past this container's own inner
        rect when scroll_snap=False) then erase just the overflow -- see
        the `scroll_snap` docstring above for why this capture/restore
        trick, rather than real clipping, is what makes partial visibility
        safe."""
        inner_x, inner_y, inner_w, inner_h = self._scroll_inner
        backups = []
        if self.main_axis == 1:
            top_h = max(0, inner_y - child.y)
            bottom_h = max(0, (child.y + child.height) - (inner_y + inner_h))
            if top_h > 0:
                backups.append((inner_x, child.y, inner_w, top_h))
            if bottom_h > 0:
                backups.append((inner_x, inner_y + inner_h, inner_w, bottom_h))
        else:
            left_w = max(0, inner_x - child.x)
            right_w = max(0, (child.x + child.width) - (inner_x + inner_w))
            if left_w > 0:
                backups.append((child.x, inner_y, left_w, inner_h))
            if right_w > 0:
                backups.append((inner_x + inner_w, inner_y, right_w, inner_h))

        captured = [(rect, self._gfx.capture_area(*rect)) for rect in backups]
        _draw(child)
        for rect, img in captured:
            self._gfx.draw_image(img, rect[0], rect[1])

    def _draw_border(self) -> None:
        b = self.border
        x, y, w, h = self.bounds.x, self.bounds.y, self.bounds.width, self.bounds.height
        # Opposite of the fill color so the border stays visible as a
        # frame instead of blending into whatever's behind it.
        fill = 0 if self.inverted else 255
        self._gfx.draw_area(x, y, w, b, fill=fill)
        self._gfx.draw_area(x, y + h - b, w, b, fill=fill)
        self._gfx.draw_area(x, y, b, h, fill=fill)
        self._gfx.draw_area(x + w - b, y, b, h, fill=fill)
        # Chamfer the 4 outer corner pixels back to background, same as
        # Menu._draw_border/TextBox._draw_border -- a bare rectangle reads
        # as a harsh square box; punching just the corner pixel softens it
        # into a rounded-looking frame without touching anything else.
        bg = 255 - fill
        self._gfx.draw_area(x, y, 1, 1, fill=bg)
        self._gfx.draw_area(x + w - 1, y, 1, 1, fill=bg)
        self._gfx.draw_area(x, y + h - 1, 1, 1, fill=bg)
        self._gfx.draw_area(x + w - 1, y + h - 1, 1, 1, fill=bg)

    def _draw_scrollbar(self) -> None:
        content_px, start_px, visible_px, viewport_px = self._scroll_metrics
        if self._gfx is None or content_px <= visible_px:
            return
        inner_x, inner_y, inner_w, inner_h = self._scroll_inner
        pos, size = scrollbar_thumb(viewport_px, content_px, start_px, visible_px)
        if self.main_axis == 1:
            self._gfx.draw_area(inner_x + inner_w, inner_y + pos, 1, size)
        else:
            self._gfx.draw_area(inner_x + pos, inner_y + inner_h, size, 1)

    def handle_key(self, keycode: str) -> bool:
        if self.scroll and self._handle_scroll_key(keycode):
            return True
        # No built-in focus model -- forward to every VISIBLE child and let
        # the first one that consumes it win (a scrolled-out-of-view child
        # shouldn't react to keys it can't be seen reacting to). Apps with
        # more than one interactive child on screen at once should route
        # explicitly instead of relying on this default.
        for child, _size in self._visible_children():
            if _handle_key(child, keycode):
                return True
        return False

    # --- scroll= internals --------------------------------------------------

    def _layout_scroll(self, inner_x: int, inner_y: int, inner_w: int, inner_h: int) -> None:
        self._scroll_inner = (inner_x, inner_y, inner_w, inner_h)
        if self.scroll_snap:
            self._layout_scroll_snap(inner_x, inner_y, inner_w, inner_h)
        else:
            self._layout_scroll_free(inner_x, inner_y, inner_w, inner_h)

    def _layout_scroll_snap(self, inner_x: int, inner_y: int, inner_w: int, inner_h: int) -> None:
        main_space = inner_h if self.main_axis == 1 else inner_w
        n = len(self.children)

        sizes: List[int] = []
        for child, _size in self.children:
            cw, ch = _measure(child, inner_w, inner_h)
            sizes.append(ch if self.main_axis == 1 else cw)

        def span(i: int, j: int) -> int:
            """Pixel width/height of children[i:j] including the gaps
            BETWEEN them (see _Stack's docstring on `spacing`)."""
            if j <= i:
                return 0
            return sum(sizes[i:j]) + self.spacing * (j - i - 1)

        def fit_forward(i: int) -> int:
            """How many children starting at i fully fit within main_space."""
            count = 0
            used = 0
            while i + count < n:
                add = sizes[i + count] + (self.spacing if count > 0 else 0)
                if used + add > main_space:
                    break
                used += add
                count += 1
            return count

        if n == 0:
            self._scroll_index = 0
            self._scroll_max_index = 0
            self._scroll_window = (0, 0)
            self._scroll_metrics = (0, 0, 0, main_space)
            return

        # Largest start index whose remaining children (i..n) still fit
        # entirely within main_space -- i.e. scrolled as far as possible
        # without leaving empty trailing space. span(i, n) is monotonically
        # non-increasing as i grows, so the smallest i satisfying it is that
        # largest valid scroll index.
        max_scroll_index = n - 1
        for i in range(n):
            if span(i, n) <= main_space:
                max_scroll_index = i
                break

        self._scroll_index = max(0, min(self._scroll_index, max_scroll_index))
        self._scroll_max_index = max_scroll_index
        visible_count = min(n - self._scroll_index, max(1, fit_forward(self._scroll_index)))
        self._scroll_window = (self._scroll_index, visible_count)
        self._scroll_metrics = (
            span(0, n),
            span(0, self._scroll_index),
            span(self._scroll_index, self._scroll_index + visible_count),
            main_space,
        )

        cursor = inner_y if self.main_axis == 1 else inner_x
        for offset in range(visible_count):
            idx = self._scroll_index + offset
            child, _size = self.children[idx]
            if self.main_axis == 1:
                _set_bounds(child, inner_x, cursor, inner_w, sizes[idx])
            else:
                _set_bounds(child, cursor, inner_y, sizes[idx], inner_h)
            cursor += sizes[idx] + self.spacing

    def _layout_scroll_free(self, inner_x: int, inner_y: int, inner_w: int, inner_h: int) -> None:
        main_space = inner_h if self.main_axis == 1 else inner_w
        n = len(self.children)

        sizes: List[int] = []
        for child, _size in self.children:
            cw, ch = _measure(child, inner_w, inner_h)
            sizes.append(ch if self.main_axis == 1 else cw)

        total = sum(sizes) + self.spacing * max(0, n - 1)
        max_offset = max(0, total - main_space)
        self._scroll_offset_px = max(0, min(self._scroll_offset_px, max_offset))
        self._scroll_max_offset_px = max_offset

        # Every child gets positioned (unlike scroll_snap, which only
        # touches the children actually in the visible window) -- some end
        # up with a main-axis position outside [0, main_space), which is
        # exactly what lets them be partially visible at either edge.
        visible_indices: List[int] = []
        cursor = -self._scroll_offset_px
        for i, (child, _size) in enumerate(self.children):
            size = sizes[i]
            if self.main_axis == 1:
                _set_bounds(child, inner_x, inner_y + cursor, inner_w, size)
            else:
                _set_bounds(child, inner_x + cursor, inner_y, size, inner_h)
            if cursor + size > 0 and cursor < main_space:
                visible_indices.append(i)
            cursor += size + self.spacing

        self._scroll_visible_indices = visible_indices
        self._scroll_metrics = (
            total,
            self._scroll_offset_px,
            min(main_space, max(0, total - self._scroll_offset_px)),
            main_space,
        )

    def _handle_scroll_key(self, keycode: str) -> bool:
        if not self.children or keycode not in ("KEY_UP", "KEY_W", "KEY_DOWN", "KEY_S"):
            return False
        if self.scroll_snap:
            previous = self._scroll_index
            if keycode in ("KEY_UP", "KEY_W"):
                self._scroll_index = max(0, self._scroll_index - 1)
            else:
                self._scroll_index = min(self._scroll_max_index, self._scroll_index + 1)
            if self._scroll_index == previous:
                return False
        else:
            previous = self._scroll_offset_px
            if keycode in ("KEY_UP", "KEY_W"):
                self._scroll_offset_px = max(0, self._scroll_offset_px - self.scroll_step)
            else:
                self._scroll_offset_px = min(self._scroll_max_offset_px, self._scroll_offset_px + self.scroll_step)
            if self._scroll_offset_px == previous:
                return False
        self._layout_scroll(*self._scroll_inner)
        self.draw()
        return True


class Column(_Stack):
    """Vertical layout group — children stack top to bottom."""

    main_axis = 1


class Row(_Stack):
    """Horizontal layout group — children stack left to right."""

    main_axis = 0


class Label:
    """A leaf text widget that measures itself against the CURRENT font
    metrics every time (so it participates correctly in layout even after
    a font/language change) instead of a fixed pixel size."""

    def __init__(self, gfx, text: str = "", font=None, fill: int = 255, align: str = "start") -> None:
        self._gfx = gfx
        self.text = text
        self.font = font
        self.fill = fill
        self.align = align  # "start" | "center" | "end"
        self.bounds = Box()

    def set_text(self, text: str) -> None:
        self.text = text

    def _font(self):
        return self.font or self._gfx.fonts["small"]

    def measure(self, available_w: int, available_h: int) -> Tuple[int, int]:
        w, h = self._gfx.get_text_size(self.text, self._font())
        return (min(w, available_w) if available_w else w, h)

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        self.bounds = Box(x, y, width, height)

    # See _Stack's identical properties in this module for why these exist:
    # every ui widget needs to share the same plain .x/.y/.width/.height
    # shape so generic movement helpers (animation.doslide) work on any of
    # them, not just the ones (Menu/TextField/ScrollPanel/TextBox) that
    # predate the Row/Column/Label self.bounds split.
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
        font = self._font()
        w, h = self._gfx.get_text_size(self.text, font)
        x = self.bounds.x
        if self.align == "center":
            x = self.bounds.x + max(0, (self.bounds.width - w) // 2)
        elif self.align == "end":
            x = self.bounds.x + max(0, self.bounds.width - w)
        y = self.bounds.y + max(0, (self.bounds.height - h) // 2)
        clear_h = max(self.bounds.height, h)
        if clear_h > 0:
            self._gfx.clear_area(self.bounds.x, self.bounds.y, self.bounds.width, clear_h)
        if self.text:
            self._gfx.draw_text(self.text, x, y, font=font, fill=self.fill)

    def handle_key(self, keycode: str) -> bool:
        return False


class Image:
    """Draws a static image or animated GIF via the `images` package --
    `size` picks which of three shapes this leaf takes:
      - None (default): the image's own natural/original size, unscaled --
        centers within whatever bounds it's actually given (which, via
        fill()/the cross-axis always getting the full inner width/height
        regardless of size tag -- see _Stack.set_bounds's Pass 2 -- can be
        bigger than the image itself).
      - FILL (the same "fill" string layout.FILL/Row/Column's `size` tag
        already uses): claims however much space fill()-tagging it gives
        it, and scales the image/GIF to fill that box while preserving
        aspect ratio (allow_upscale defaults to True in this case, since
        "fill the box" implies scaling up a smaller source image).
      - a fixed int: centers a size x size box within whatever bounds it's
        actually given, same as `None` but at an explicit forced size
        instead of the image's real dimensions.
    All three started as private per-app leaf widgets (_Swatch/_FillImage
    in ui_test) before being promoted here once it was clear neither was
    actually test-specific.

    GIF-ness is auto-detected from the path's extension -- ticked via
    update(dt) like animation.SlideIn/ScaleIn once drawn; .anim is None
    for a static image (nothing to tick)."""

    def __init__(
        self, images: Any, gfx: Any, path: str, size: Union[int, str, None] = None,
        loop: bool = True, allow_upscale: Optional[bool] = None,
    ) -> None:
        self._images = images
        self._gfx = gfx
        self.path = path
        self.size = size
        self.loop = loop
        self.allow_upscale = allow_upscale if allow_upscale is not None else (size == FILL)
        self.anim = None
        self._natural_cache: Optional[Dict[str, Any]] = None
        self.bounds = Box()

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

    def _is_gif(self) -> bool:
        return self.path.lower().endswith(".gif")

    def _load(self, max_width: Optional[int], max_height: Optional[int]) -> Dict[str, Any]:
        if self._is_gif():
            return self._images.load_animation_file(
                self.path, max_width=max_width, max_height=max_height, allow_upscale=self.allow_upscale
            )
        return self._images.load_file(
            self.path, max_width=max_width, max_height=max_height, allow_upscale=self.allow_upscale
        )

    def _natural_data(self) -> Dict[str, Any]:
        # max_width/max_height=None -> _target_size (utils/image_utils.py)
        # returns the source's own dimensions unscaled. Cached: measure()
        # and draw() would otherwise each decode (and, for a GIF, dither
        # every frame of) the same file separately.
        if self._natural_cache is None:
            self._natural_cache = self._load(None, None)
        return self._natural_cache

    def measure(self, available_w: int, available_h: int) -> Tuple[int, int]:
        if self.size == FILL:
            return (available_w, available_h)
        if self.size is not None:
            return (self.size, self.size)
        if not self.path or not os.path.isfile(self.path):
            return (0, 0)
        data = self._natural_data()
        return (data["width"], data["height"])

    def set_bounds(self, x: int, y: int, width: int, height: int) -> None:
        self.bounds = Box(x, y, width, height)

    def draw(self) -> None:
        self._gfx.clear_area(self.bounds.x, self.bounds.y, self.bounds.width, self.bounds.height)
        self.anim = None
        if not self.path or not os.path.isfile(self.path):
            return
        if self.size == FILL:
            data = self._load(self.bounds.width, self.bounds.height)
        elif self.size is not None:
            data = self._load(self.size, self.size)
        else:
            data = self._natural_data()

        ox = self.bounds.x + max(0, (self.bounds.width - data["width"]) // 2)
        oy = self.bounds.y + max(0, (self.bounds.height - data["height"]) // 2)
        if self._is_gif():
            self.anim = self._images.make_animation(data, ox, oy, loop=self.loop)
        else:
            self._gfx.draw_image(data["image"], ox, oy)

    def update(self, dt: float) -> None:
        if self.anim is not None:
            self.anim.update(dt)

    def handle_key(self, keycode: str) -> bool:
        return False
