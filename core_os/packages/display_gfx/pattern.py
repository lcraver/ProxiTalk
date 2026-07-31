"""8x8 ordered-dither patterns -- mirrors Playdate's LCDPattern (8 rows of
8 bits, MSB-first) so a fill can simulate a gray level on this 1-bit
display instead of only flat black/white.

Each row's bit at position (7-x) says whether column x is "on" (drawn with
the fill color) or "off" (drawn with the background color) -- draw_gfx's
draw_area_pattern tiles this 8x8 tile across whatever rect it's asked to
fill, the same way Playdate tiles an LCDPattern across a fillRect.
"""

from __future__ import annotations

from typing import Tuple

Pattern = Tuple[int, int, int, int, int, int, int, int]

# Classic 8x8 Bayer ordered-dither threshold matrix (values 0-63) -- used by
# from_coverage() to turn a 0..1 gray fraction into a bit pattern, and to
# build the named presets below.
_BAYER8 = (
    (0, 32, 8, 40, 2, 34, 10, 42),
    (48, 16, 56, 24, 50, 18, 58, 26),
    (12, 44, 4, 36, 14, 46, 6, 38),
    (60, 28, 52, 20, 62, 30, 54, 22),
    (3, 35, 11, 43, 1, 33, 9, 41),
    (51, 19, 59, 27, 49, 17, 57, 25),
    (15, 47, 7, 39, 13, 45, 5, 37),
    (63, 31, 55, 23, 61, 29, 53, 21),
)


def from_coverage(coverage: float) -> Pattern:
    """Build an 8x8 pattern where roughly `coverage` (0..1) of pixels are
    "on" -- e.g. from_coverage(0.5) is a 50% gray checkerboard-ish
    dither. Uses the Bayer8x8 threshold matrix so adjacent coverage
    levels differ by exactly one pixel toggling, not a random-looking
    jump, matching how Playdate's Bayer8x8 dither type behaves."""
    threshold = round(coverage * 64)
    rows = []
    for row in _BAYER8:
        byte = 0
        for value in row:
            byte = (byte << 1) | (1 if value < threshold else 0)
        rows.append(byte)
    return tuple(rows)  # type: ignore[return-value]


def from_bits(rows: Tuple[int, int, int, int, int, int, int, int]) -> Pattern:
    """Custom pattern from 8 raw row-bytes, MSB-first per row -- for
    non-dither patterns (stripes, checkerboard, brick, etc.) that
    from_coverage's Bayer threshold can't express."""
    return tuple(rows)  # type: ignore[return-value]


WHITE: Pattern = from_coverage(1.0)
BLACK: Pattern = from_coverage(0.0)
GRAY_87_5: Pattern = from_coverage(0.875)
GRAY_75: Pattern = from_coverage(0.75)
GRAY_62_5: Pattern = from_coverage(0.625)
GRAY_50: Pattern = from_coverage(0.5)
GRAY_37_5: Pattern = from_coverage(0.375)
GRAY_25: Pattern = from_coverage(0.25)
GRAY_12_5: Pattern = from_coverage(0.125)

PRESETS = {
    "white": WHITE,
    "black": BLACK,
    "gray-87.5": GRAY_87_5,
    "gray-75": GRAY_75,
    "gray-62.5": GRAY_62_5,
    "gray-50": GRAY_50,
    "gray-37.5": GRAY_37_5,
    "gray-25": GRAY_25,
    "gray-12.5": GRAY_12_5,
}
