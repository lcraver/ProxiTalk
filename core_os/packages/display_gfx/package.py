"""display_gfx package — drawing primitives, layers, batching, fonts, cursor
control. Built directly on core.display; owns three composited PIL layers
(base, overlay, cursor) combined via per-layer masks (Image.paste with a mask
image, so undrawn areas of overlay/cursor stay transparent to the layer below).

Runs entirely on the single cooperative scheduler thread — app update()/
onkeydown() calls, and Package-delivered background-task callbacks, both
happen on the main thread (see core/scheduler.py) — so unlike V1's threaded
design, no internal command queue or background compositor thread is needed
here; draws apply directly and flush immediately (or on end_batch()).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from core_os.packages.base import Package, PackageResources
from core_os.packages.display_gfx import pattern as pattern_module
from core_os.packages.display_gfx.pattern import Pattern


class _Layer:
    def __init__(self, size: Tuple[int, int], on_mark: Optional[Callable[[int, int, int, int], None]] = None) -> None:
        self.size = size
        self.image = Image.new("1", size, 0)
        self.mask = Image.new("1", size, 0)
        self._on_mark = on_mark

    def clear(self) -> None:
        self.image = Image.new("1", self.size, 0)
        self.mask = Image.new("1", self.size, 0)

    def clear_area(self, x: int, y: int, w: int, h: int) -> None:
        if w <= 0 or h <= 0:
            return
        ImageDraw.Draw(self.image).rectangle([x, y, x + w - 1, y + h - 1], fill=0)
        ImageDraw.Draw(self.mask).rectangle([x, y, x + w - 1, y + h - 1], fill=0)

    def mark(self, x: int, y: int, w: int, h: int) -> None:
        ImageDraw.Draw(self.mask).rectangle([x, y, x + max(w, 1) - 1, y + max(h, 1) - 1], fill=1)
        if self._on_mark:
            self._on_mark(x, y, w, h)


class DisplayGfxPackage(Package):
    package_id = "display_gfx"
    display_name = "Display Graphics"
    priority = 10
    capability_tags = {"drawing", "layers", "fonts"}
    core_requires = {"display"}

    def initialize(self) -> None:
        display = self.resources.core.display
        size = (display.width, display.height)
        self.size = size

        def _forward_debug_region(x: int, y: int, w: int, h: int) -> None:
            fn = getattr(display, "add_debug_region", None)
            if fn:
                fn(x, y, w, h)

        self._base = _Layer(size, on_mark=_forward_debug_region)
        self._overlay = _Layer(size, on_mark=_forward_debug_region)
        self._cursor = _Layer(size, on_mark=_forward_debug_region)
        self._batch_depth = 0
        self._cursor_enabled = False

        self._display = display

        font_path = self.resources.paths.get("font_path")
        # misaki_gothic.ttf embeds bitmap strikes only at multiples of its
        # native 8x8 pixel grid (8/16/24/...) — any other size forces
        # FreeType to interpolate the strike and comes out garbled/illegible.
        #
        # One font, one size (8px), covers both Latin and Japanese glyphs —
        # unlike the old split pixel.ttf ("small", ASCII-only)/LanaPixel.ttf
        # ("default", Japanese-capable but a different size), so "small" and
        # "default" are just two names for the SAME font object below. Kept
        # as separate dict keys rather than collapsed to one, since call
        # sites across the codebase already reference fonts["small"]
        # directly (see _resolve_font, now a thin passthrough since there's
        # no longer a smaller/bigger font to switch between).
        try:
            base_font = ImageFont.truetype(font_path, 8) if font_path else ImageFont.load_default()
            self.fonts: Dict[str, Any] = {
                "small": base_font,
                "default": base_font,
                "large": ImageFont.truetype(font_path, 16) if font_path else ImageFont.load_default(),
            }
        except Exception as exc:
            print(f"[display_gfx] Failed to load fonts, falling back to PIL default: {exc}")
            default_font = ImageFont.load_default()
            self.fonts = {"small": default_font, "default": default_font, "large": default_font}

        self._flush()

    # --- collider debug overlay --------------------------------------------
    # Package-internal (attribute access, like draw_image/clear_area below) --
    # SpriteList holds this same DisplayGfxPackage instance (see sprite.py's
    # own docstring on that convention), not the app-facing context dict, so
    # these aren't in get_public_api. Forwards to the backend the same
    # defensive-getattr way _forward_debug_region does above: device_pi has
    # no F2 dev HUD to feed, so these are no-ops there.

    def clear_collider_regions(self) -> None:
        fn = getattr(self._display, "clear_collider_regions", None)
        if fn:
            fn()

    def report_collider(self, x: int, y: int, width: int, height: int) -> None:
        fn = getattr(self._display, "add_collider_region", None)
        if fn:
            fn(x, y, width, height)

    # --- compositing ------------------------------------------------------

    def _composite(self) -> Image.Image:
        frame = self._base.image.copy()
        frame.paste(self._overlay.image, (0, 0), self._overlay.mask)
        frame.paste(self._cursor.image, (0, 0), self._cursor.mask)
        return frame

    def _flush(self) -> None:
        if self._batch_depth > 0:
            return
        display = self.resources.core.display
        display.image(self._composite())
        display.show()

    def snapshot(self) -> Image.Image:
        """The full composited frame, right now — lets a caller that's
        about to blank the display (sleep) restore exactly what was showing
        afterward, without every app needing its own redraw-on-resume
        logic. See restore()."""
        return self._composite().copy()

    def restore(self, frame: Image.Image) -> None:
        """Restore a frame captured by snapshot(). Flattened into the base
        layer; overlay/cursor are cleared since whatever was on them either
        gets restarted by the caller (see sleep's suspended-overlay restart)
        or wasn't meant to persist (e.g. cursor blink phase)."""
        self._base.image = frame.copy()
        self._overlay.clear()
        self._cursor.clear()
        self._flush()

    # --- base layer ---------------------------------------------------------

    def _resolve_font(self, text: str, font):
        """Just `font or the default font` -- text/font param are still
        accepted (and every call site still passes them) because this used
        to auto-upgrade "small" (pixel.ttf, no Japanese glyphs) to "default"
        (LanaPixel.ttf) for non-ASCII text or Japanese-mode strings. Now
        that both keys are the SAME misaki_gothic.ttf font object (see
        initialize()), there's nothing left to upgrade to -- every caller
        already gets full Latin+Japanese coverage from whatever font they
        pass. Kept as a real method rather than inlined at each call site
        so a future split font doesn't require re-threading text/language
        lookups through every draw_text/measure_ink/etc. call again."""
        return font or self.fonts["default"]

    def _top_overhang(self, text: str, font) -> int:
        """Pixels to shift the draw position by so ink starts EXACTLY at
        the nominal y, for any font/text. Always 0 for misaki_gothic.ttf
        (verified: its glyphs render flush with a (0, 0)-origin bbox, no
        top bearing at all — a strict bitmap font, unlike the old split
        pixel.ttf/LanaPixel.ttf pair this used to correct for, where
        pixel.ttf's Latin glyphs had a positive top bearing and
        LanaPixel.ttf's kana glyphs a negative one, in opposite
        directions from each other. Computed fresh via a real textbbox()
        call rather than hardcoded to 0, so this keeps working without
        another audit if the font ever changes again."""
        bbox = ImageDraw.Draw(self._base.image).textbbox((0, 0), text, font=font)
        return -bbox[1]

    def draw_text(self, text: str, x: int, y: int, font=None, fill: int = 255) -> None:
        f = self._resolve_font(text, font)
        draw_y = y + self._top_overhang(text, f)
        ImageDraw.Draw(self._base.image).text((x, draw_y), text, font=f, fill=fill)
        self._base.mark(*self._text_bbox(text, f, x, y))
        self._flush()

    def draw_text_inverted(self, text: str, x: int, y: int, font=None, padding: int = 1) -> None:
        f = self._resolve_font(text, font)
        draw_y = y + self._top_overhang(text, f)
        # Measure the real ink bounding box AT the (compensated) draw
        # position, not at (0, 0) — pixel fonts commonly have a nonzero top
        # offset (glyphs start a pixel or two below/above the nominal draw
        # point), and reusing get_text_size's (0,0)-based w/h here silently
        # dropped that offset, making the highlight box both taller than
        # the actual glyphs and vertically misaligned with them.
        bbox = ImageDraw.Draw(self._base.image).textbbox((x, draw_y), text, font=f)
        rx, ry = bbox[0] - padding, bbox[1] - padding
        rw, rh = (bbox[2] - bbox[0]) + padding * 2, (bbox[3] - bbox[1]) + padding * 2
        # Clamp the top/left edge to (x, y): the padding halo must not push
        # the highlight box above/left of the position the caller asked
        # for. Without this, a widget drawing inverted text flush against
        # its own top edge (e.g. TextField's suggestion on its first row,
        # sitting directly under a title with zero margin) bleeds `padding`
        # pixels into whatever's drawn there — verified: misaki_gothic.ttf's
        # zero top bearing gives bbox[1] == draw_y == y, so
        # bbox[1] - padding lands one row ABOVE y, overwriting the sibling
        # above instead of clipping harmlessly off-canvas the way row-0
        # cases do (there's no row -1 to clip against, but there IS a row
        # y-1 that belongs to whatever's drawn above this widget).
        if ry < y:
            rh -= y - ry
            ry = y
        if rx < x:
            rw -= x - rx
            rx = x
        ImageDraw.Draw(self._base.image).rectangle([rx, ry, rx + rw - 1, ry + rh - 1], fill=255)
        ImageDraw.Draw(self._base.image).text((x, draw_y), text, font=f, fill=0)
        self._base.mark(rx, ry, rw, rh)
        self._flush()

    def draw_image(self, img, x: int, y: int) -> None:
        self._base.image.paste(img, (x, y))
        self._base.mark(x, y, img.width, img.height)
        self._flush()

    def capture_area(self, x: int, y: int, w: int, h: int) -> Image.Image:
        """Snapshot of the BASE layer's current pixels within this exact
        rect, with no side effect on the display itself. Used by
        ui.layout._Stack's `scroll_snap=False` clipping trick: capture the
        strip a partially-visible child is about to overdraw BEFORE it
        draws, then draw_image() it straight back after -- erasing just
        that child's overflow ink while leaving whatever was legitimately
        there (a sibling widget, empty padding) untouched, without this
        package needing any real clip-region/mask primitive."""
        if w <= 0 or h <= 0:
            return self._base.image.crop((0, 0, 0, 0))
        return self._base.image.crop((x, y, x + w, y + h))

    def draw_area(self, x: int, y: int, width: int, height: int, fill: int = 255) -> None:
        ImageDraw.Draw(self._base.image).rectangle([x, y, x + width - 1, y + height - 1], fill=fill)
        self._base.mark(x, y, width, height)
        self._flush()

    def _paint_pattern(
        self, image: Image.Image, x: int, y: int, width: int, height: int,
        pattern: Pattern, fill: int, bg: int,
        radius: int = 0, corners: Optional[Tuple[bool, bool, bool, bool]] = None,
    ) -> None:
        # One 8x8 tile built once, then pasted across the rect in 8px
        # steps -- cheaper than a per-pixel Python loop over the whole
        # rect, and needs no numpy (nothing else in this package uses it).
        tile = Image.new("1", (8, 8))
        tile.putdata([fill if (row >> (7 - col)) & 1 else bg for row in pattern for col in range(8)])
        # radius>0: only paste where a rounded-rect mask says "inside" --
        # e.g. a dithered card cell that happens to sit in the card's own
        # rounded corner shouldn't square that corner back off by painting
        # over it edge-to-edge (see modifier_hud's dithered special keys,
        # which can land in the same cell as the card's rounded top edge).
        mask = None
        if radius > 0:
            mask = Image.new("1", (width, height), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, width - 1, height - 1], radius=radius, fill=1, corners=corners)
        for ty in range(0, height, 8):
            th = min(8, height - ty)
            for tx in range(0, width, 8):
                tw = min(8, width - tx)
                chunk = tile if (tw, th) == (8, 8) else tile.crop((0, 0, tw, th))
                mask_chunk = mask.crop((tx, ty, tx + tw, ty + th)) if mask is not None else None
                image.paste(chunk, (x + tx, y + ty), mask=mask_chunk)

    def draw_area_pattern(
        self, x: int, y: int, width: int, height: int,
        pattern: Pattern, fill: int = 255, bg: int = 0,
    ) -> None:
        if width <= 0 or height <= 0:
            return
        self._paint_pattern(self._base.image, x, y, width, height, pattern, fill, bg)
        self._base.mark(x, y, width, height)
        self._flush()

    def invert_area(self, x: int, y: int, width: int, height: int) -> None:
        """Flip every pixel in this rect: 0<->255. Used for "inverted"
        containers (ui.layout._Stack's `inverted`) — rather than asking
        every possible child widget to know how to draw itself in black-on-
        white, the container just lets children draw normally (white ink on
        the default black background) and inverts the whole rect afterward,
        which turns that into black ink on a white background regardless of
        what was actually drawn there."""
        if width <= 0 or height <= 0:
            return
        box = (x, y, x + width, y + height)
        region = self._base.image.crop(box)
        self._base.image.paste(region.point(lambda p: 255 - p), (x, y))
        self._base.mark(x, y, width, height)
        self._flush()

    def clear_area(self, x: int, y: int, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            return
        self._base.clear_area(x, y, width, height)
        self._flush()

    def clear_screen(self) -> None:
        self._base.clear()
        self._flush()

    # --- overlay layer --------------------------------------------------

    def draw_overlay_text(self, text: str, x: int, y: int, font=None, fill: int = 255) -> None:
        f = self._resolve_font(text, font)
        draw_y = y + self._top_overhang(text, f)
        ImageDraw.Draw(self._overlay.image).text((x, draw_y), text, font=f, fill=fill)
        self._overlay.mark(*self._text_bbox(text, f, x, y))
        self._flush()

    def draw_overlay_text_inverted(self, text: str, x: int, y: int, font=None, padding: int = 1) -> None:
        f = self._resolve_font(text, font)
        draw_y = y + self._top_overhang(text, f)
        bbox = ImageDraw.Draw(self._overlay.image).textbbox((x, draw_y), text, font=f)
        rx, ry = bbox[0] - padding, bbox[1] - padding
        rw, rh = (bbox[2] - bbox[0]) + padding * 2, (bbox[3] - bbox[1]) + padding * 2
        # See draw_text_inverted's identical clamp — the padding halo must
        # not push the highlight box above/left of the caller's (x, y).
        if ry < y:
            rh -= y - ry
            ry = y
        if rx < x:
            rw -= x - rx
            rx = x
        ImageDraw.Draw(self._overlay.image).rectangle([rx, ry, rx + rw - 1, ry + rh - 1], fill=255)
        ImageDraw.Draw(self._overlay.image).text((x, draw_y), text, font=f, fill=0)
        self._overlay.mark(rx, ry, rw, rh)
        self._flush()

    def draw_overlay_image(self, img, x: int, y: int) -> None:
        self._overlay.image.paste(img, (x, y))
        self._overlay.mark(x, y, img.width, img.height)
        self._flush()

    def draw_overlay_area(
        self, x: int, y: int, width: int, height: int, fill: int = 255,
        radius: int = 0, corners: Optional[Tuple[bool, bool, bool, bool]] = None,
    ) -> None:
        box = [x, y, x + width - 1, y + height - 1]
        if radius > 0:
            # corners is (top_left, top_right, bottom_right, bottom_left) --
            # None means all four, matching ImageDraw.rounded_rectangle's own
            # default, so passing just `radius` still rounds the whole rect.
            ImageDraw.Draw(self._overlay.image).rounded_rectangle(box, radius=radius, fill=fill, corners=corners)
        else:
            ImageDraw.Draw(self._overlay.image).rectangle(box, fill=fill)
        self._overlay.mark(x, y, width, height)
        self._flush()

    def draw_overlay_area_pattern(
        self, x: int, y: int, width: int, height: int,
        pattern: Pattern, fill: int = 255, bg: int = 0,
        radius: int = 0, corners: Optional[Tuple[bool, bool, bool, bool]] = None,
    ) -> None:
        if width <= 0 or height <= 0:
            return
        self._paint_pattern(self._overlay.image, x, y, width, height, pattern, fill, bg, radius, corners)
        self._overlay.mark(x, y, width, height)
        self._flush()

    def clear_overlay_area(self, x: int, y: int, width: int, height: int) -> None:
        self._overlay.clear_area(x, y, width, height)
        self._flush()

    # --- cursor layer -----------------------------------------------------

    def set_cursor_enabled(self, enabled: bool) -> None:
        self._cursor_enabled = enabled
        if not enabled:
            self._cursor.clear()
            self._flush()

    def set_app_cursor_enabled(self, enabled: bool) -> None:
        self.set_cursor_enabled(enabled)

    def set_cursor_position(self, x: int, y: int) -> None:
        if not self._cursor_enabled:
            return
        self._cursor.clear()
        ImageDraw.Draw(self._cursor.image).rectangle([x, y, x + 1, y + 9], fill=255)
        self._cursor.mark(x, y, 2, 10)
        self._flush()

    def clear_cursor_area(self) -> None:
        self._cursor.clear()
        self._flush()

    # --- batching ---------------------------------------------------------

    def begin_batch(self) -> None:
        self._batch_depth += 1

    def end_batch(self) -> None:
        self._batch_depth = max(0, self._batch_depth - 1)
        self._flush()

    def update_region(self, x: int, y: int, width: int, height: int) -> None:
        self._flush()

    # --- text metrics -----------------------------------------------------

    def get_text_size(self, text: str, font=None) -> Tuple[int, int]:
        # Must resolve the font the same way draw_text() does, so wrapping
        # math (Menu/TextField/ScrollPanel all measure before drawing) is
        # computed against whatever font will actually render the glyphs.
        #
        # Height is the tight glyph span (bbox[3]-bbox[0]... i.e.
        # bbox[3]-bbox[1]) — safe to use directly now that _top_overhang
        # shifts the actual draw position (both directions, not just one)
        # so ink always starts exactly at the nominal y. A caller that
        # allocates exactly this many pixels gets a box that neither clips
        # (draw_text no longer renders anything outside it) nor leaves a
        # gap (nothing is over-allocated for bearing that draw_text has
        # already cancelled out).
        f = self._resolve_font(text, font)
        bbox = ImageDraw.Draw(self._base.image).textbbox((0, 0), text, font=f)
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])

    def measure_ink(self, text: str, font=None) -> Tuple[int, int]:
        """Tight (width, height) of text as ACTUALLY rendered — a real
        render pass to a scratch image, scanned for lit pixels via
        Image.getbbox(), not the font's metric-reported advance-width bbox
        get_text_size() uses. The two aren't always the same: verified for
        misaki_gothic.ttf, get_text_size("Apples") reports width 24, but the
        pixels ImageDraw.text() actually paints only span 23 columns —
        PIL's textbbox() is computed from the font's glyph-advance tables,
        which can overshoot the real raster by a pixel for some bitmap
        fonts at small sizes. Invisible almost everywhere (wrap/layout
        math has slack to spare), but very visible in something drawn
        pixel-tight around the text, like Menu's selected-row highlight.

        Meaningfully slower than get_text_size (an actual render, not a
        metrics lookup) — use it only where pixel-perfect tightness
        matters, not in a hot path like wrap_text's per-substring checks."""
        return self.ink_bbox(text, font)[2:]

    def ink_bbox(self, text: str, font=None) -> Tuple[int, int, int, int]:
        """Tight ink bounding box for `text` drawn at a nominal (0, 0), as
        (left, top, width, height) — left/top being how far the real
        pixels sit from that nominal point, width/height the same tight
        span measure_ink() returns.

        top is always 0: _top_overhang already shifts draw_text's actual
        draw position so ink starts exactly at the nominal y, for every
        font (see its docstring). `left` is also always 0 for
        misaki_gothic.ttf (verified across Latin and kana: no left
        bearing at all, a strict bitmap font) — but nothing compensates
        the x axis the way _top_overhang compensates y, since draw_text
        draws at plain x, so a future font whose glyphs DO carry a left
        bearing would leave `left` nonzero. A caller that draws text at
        (x, y) and then boxes a halo/highlight around it using only
        measure_ink's width — assuming ink starts exactly at x — would
        end up with a halo shifted off the real ink in that case: too
        much padding on one side, too little on the other. Add `left`
        to x before boxing to stay correct either way."""
        f = self._resolve_font(text, font)
        w, h = self.get_text_size(text, f)
        if w <= 0 or h <= 0:
            return (0, 0, 0, 0)
        pad = 2
        scratch = Image.new("1", (w + pad * 2, h + pad * 2), 0)
        draw_x = pad
        draw_y = pad + self._top_overhang(text, f)
        ImageDraw.Draw(scratch).text((draw_x, draw_y), text, font=f, fill=255)
        bbox = scratch.getbbox()
        if bbox is None:
            return (0, 0, 0, 0)
        return (bbox[0] - draw_x, bbox[1] - draw_y, bbox[2] - bbox[0], bbox[3] - bbox[1])

    def _text_bbox(self, text: str, font, x: int, y: int) -> Tuple[int, int, int, int]:
        w, h = self.get_text_size(text, font)
        return (x, y, max(w, 1), max(h, 1))

    def line_height(self, text: str = "", font=None) -> int:
        """Row height (glyph height + 1px inter-line gap) to allocate for
        a line of TEXT at this font — measured against the text that will
        actually be drawn, not a fixed reference string. Widgets used to
        each hardcode "Ag" (a Latin ascender+descender) for this; that's a
        reasonable stand-in for English text, but script-specific glyphs
        can measure a different height (verified: misaki_gothic.ttf's kana
        fill its full 8px cell, 1px TALLER than "Ag"'s 7px), clipping the
        bottom row of Japanese text if "Ag" were used unconditionally.
        Falls back to "Ag" only for empty text, where there's nothing real
        to measure.

        Callers building a multi-line box height from this should use
        (n-1) * line_height(...) + get_text_size(text, font)[1] for n
        lines — NOT n * line_height(...) — since the "+1" here is the gap
        BETWEEN rows, not part of any single row's own height; multiplying
        by n reserves a trailing gap after the last line that nothing
        follows (verified: this exact off-by-one in proxi's speaking-
        status popup left a 1px dead strip under single-line messages)."""
        _, h = self.get_text_size(text or "Ag", font)
        return h + 1

    def wrap_text(self, text: str, width: int, font=None) -> "list[str]":
        """Greedy wrap `text` to fit within `width` px at this font's real
        metrics — the one implementation every wrapping widget
        (Menu/ScrollPanel/TextField/TextBox) should share instead of each
        reimplementing the same loop against get_text_size with its own
        subtly different edge cases.

        Breaks on whitespace for Latin text, same as a plain word-wrap. But
        Japanese has no inter-word spaces at all — `text.split()` on a pure
        Japanese sentence returns ONE "word" (the whole sentence), which
        either fits or overflows the width outright with nowhere to break.
        Each CJK character is instead its own breakable unit (Japanese line-
        breaking conventions allow a break between almost any two characters,
        unlike Latin script where breaking mid-word is wrong), so a long
        Japanese line still wraps -- just at a character boundary instead of
        a word boundary. Latin runs and the original spacing between them
        are preserved as-is via `_wrap_units`."""
        lines: "list[str]" = []
        current = ""
        for unit, space_before in self._wrap_units(text):
            trial = f"{current} {unit}" if current and space_before else current + unit
            w, _ = self.get_text_size(trial, font)
            if w > width and current:
                lines.append(current)
                current = unit
            else:
                current = trial
        if current:
            lines.append(current)
        return lines or [""]

    _CJK_RANGES = (
        (0x3000, 0x303F),  # CJK punctuation (、。「」etc.)
        (0x3040, 0x30FF),  # hiragana + katakana
        (0x4E00, 0x9FFF),  # CJK unified ideographs (kanji)
        (0xFF00, 0xFFEF),  # fullwidth forms
    )

    @classmethod
    def _is_cjk(cls, ch: str) -> bool:
        code = ord(ch)
        return any(lo <= code <= hi for lo, hi in cls._CJK_RANGES)

    @classmethod
    def _wrap_units(cls, text: str) -> "list[Tuple[str, bool]]":
        """Split `text` into (unit, space_before) pairs for wrap_text: a
        unit is either a single CJK character (its own breakable unit) or a
        maximal run of other non-space characters (a Latin "word", kept
        whole). `space_before` records whether real whitespace preceded
        this unit in the source, so wrap_text only re-inserts a space where
        one actually existed -- CJK units never get one, matching how
        Japanese is normally written with no spaces between characters."""
        units: "list[Tuple[str, bool]]" = []
        buf = ""
        space_pending = False
        for ch in text:
            if ch.isspace():
                if buf:
                    units.append((buf, space_pending))
                    buf = ""
                space_pending = True
                continue
            if cls._is_cjk(ch):
                if buf:
                    units.append((buf, space_pending))
                    buf = ""
                    space_pending = False
                units.append((ch, space_pending))
                space_pending = False
                continue
            buf += ch
        if buf:
            units.append((buf, space_pending))
        return units

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "draw_text": self.draw_text,
            "draw_text_inverted": self.draw_text_inverted,
            "draw_image": self.draw_image,
            "draw_area": self.draw_area,
            "draw_area_pattern": self.draw_area_pattern,
            "invert_area": self.invert_area,
            "capture_area": self.capture_area,
            "clear_area": self.clear_area,
            "clear_screen": self.clear_screen,
            "draw_overlay_text": self.draw_overlay_text,
            "draw_overlay_text_inverted": self.draw_overlay_text_inverted,
            "draw_overlay_image": self.draw_overlay_image,
            "draw_overlay_area": self.draw_overlay_area,
            "draw_overlay_area_pattern": self.draw_overlay_area_pattern,
            "clear_overlay_area": self.clear_overlay_area,
            "patterns": pattern_module.PRESETS,
            "make_pattern": pattern_module.from_coverage,
            "begin_batch": self.begin_batch,
            "end_batch": self.end_batch,
            "update_region": self.update_region,
            "get_text_size": self.get_text_size,
            "measure_ink": self.measure_ink,
            "ink_bbox": self.ink_bbox,
            "line_height": self.line_height,
            "wrap_text": self.wrap_text,
            "fonts": self.fonts,
            "set_cursor_enabled": self.set_cursor_enabled,
            "set_app_cursor_enabled": self.set_app_cursor_enabled,
            "set_cursor_position": self.set_cursor_position,
            "clear_cursor_area": self.clear_cursor_area,
        }


AVAILABLE_PACKAGES = [DisplayGfxPackage]
