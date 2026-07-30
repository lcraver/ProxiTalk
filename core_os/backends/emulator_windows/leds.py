"""No-op LED driver — a Windows dev PC has no RGB hardware attached."""

from __future__ import annotations

from typing import List, Tuple

from core_os.core.drivers.base import LedDriver


class NullLedDriver(LedDriver):
    def __init__(self, num_leds: int = 4) -> None:
        self.num_leds = num_leds

    def set_pixels(self, pixels: List[Tuple[int, int, int]], brightness: int = 8) -> None:
        pass

    def clear(self) -> None:
        pass

    def stop(self) -> None:
        pass
