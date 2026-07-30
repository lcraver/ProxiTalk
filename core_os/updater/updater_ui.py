"""updater_ui.py — minimal boot-time screen for the update check.

Drawn directly onto a DisplayDriver via PIL, following the same convention as
display_gfx (mode '1', 0=off, 255=on text) but without depending on it --
display_gfx is a Package, and the whole Package/event-bus/scheduler stack
doesn't exist yet at the point run_auto_update() runs (before
compose.build_core_registry()). This talks to the raw DisplayDriver contract
only.
"""

from __future__ import annotations

from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from core_os.core.drivers.base import DisplayDriver


class UpdaterUI:
    def __init__(
        self,
        display: DisplayDriver,
        font_path: Optional[str] = None,
        font_small_path: Optional[str] = None,
    ) -> None:
        self._display = display
        try:
            # misaki_gothic.ttf's embedded bitmap strikes only exist at
            # multiples of its native 8x8 grid; other sizes render garbled.
            self._font = ImageFont.truetype(font_path, 8) if font_path else ImageFont.load_default()
            self._font_small = ImageFont.truetype(font_small_path, 8) if font_small_path else self._font
        except Exception:
            self._font = ImageFont.load_default()
            self._font_small = self._font

    def _blank(self) -> Image.Image:
        return Image.new("1", (self._display.width, self._display.height), 0)

    def _line_height(self, draw: ImageDraw.ImageDraw, font) -> int:
        bbox = draw.textbbox((0, 0), "Ayg", font=font)
        return (bbox[3] - bbox[1]) + 4

    def show_lines(self, lines: List[str], font=None) -> None:
        f = font or self._font
        img = self._blank()
        draw = ImageDraw.Draw(img)
        line_height = self._line_height(draw, f)
        total_height = line_height * len(lines)
        y = max(0, (self._display.height - total_height) // 2)
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=f)
            w = bbox[2] - bbox[0]
            x = max(0, (self._display.width - w) // 2)
            draw.text((x, y), line, font=f, fill=255)
            y += line_height
        self._display.image(img)
        self._display.show()

    def show_progress(self, message: str, fraction: float) -> None:
        fraction = max(0.0, min(1.0, fraction))
        img = self._blank()
        draw = ImageDraw.Draw(img)

        bbox = draw.textbbox((0, 0), message, font=self._font)
        w = bbox[2] - bbox[0]
        x = max(0, (self._display.width - w) // 2)
        text_y = self._display.height // 2 - 14
        draw.text((x, text_y), message, font=self._font, fill=255)

        bar_w = int(self._display.width * 0.7)
        bar_h = 6
        bar_x = (self._display.width - bar_w) // 2
        bar_y = self._display.height // 2 + 4
        draw.rectangle([bar_x, bar_y, bar_x + bar_w - 1, bar_y + bar_h - 1], outline=255, fill=0)
        fill_w = int((bar_w - 2) * fraction)
        if fill_w > 0:
            draw.rectangle([bar_x + 1, bar_y + 1, bar_x + fill_w, bar_y + bar_h - 2], fill=255)

        percent = f"{int(fraction * 100)}%"
        pbbox = draw.textbbox((0, 0), percent, font=self._font_small)
        pw = pbbox[2] - pbbox[0]
        draw.text((max(0, (self._display.width - pw) // 2), bar_y + bar_h + 4), percent, font=self._font_small, fill=255)

        self._display.image(img)
        self._display.show()
