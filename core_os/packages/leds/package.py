"""leds package — solid/blink/chase effects over core.leds. Brand new
capability (V1 never exposed the SK9822 LEDs to apps). Animations run on a
dedicated lightweight background thread — independent of app update cadence
and non-blocking for the rest of the system, same non-blocking guarantee as
V1's audio streaming — rather than the app-dispatch thread."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from core_os.packages.base import Package, PackageResources


class LedsPackage(Package):
    package_id = "leds"
    display_name = "RGB LEDs"
    priority = 40
    capability_tags = {"leds", "effects"}
    core_requires = {"leds"}

    def initialize(self) -> None:
        self._anim_thread: Optional[threading.Thread] = None
        self._anim_stop = threading.Event()

    def shutdown(self) -> None:
        self.off()

    def _stop_animation(self) -> None:
        self._anim_stop.set()
        if self._anim_thread is not None and self._anim_thread.is_alive():
            self._anim_thread.join(timeout=1.0)
        self._anim_stop.clear()

    def set_solid(self, r: int, g: int, b: int, brightness: int = 8) -> None:
        self._stop_animation()
        leds = self.resources.core.leds
        leds.set_pixels([(r, g, b)] * leds.num_leds, brightness=brightness)

    def set_pixel(self, index: int, r: int, g: int, b: int, brightness: int = 8) -> None:
        self._stop_animation()
        leds = self.resources.core.leds
        pixels = [(0, 0, 0)] * leds.num_leds
        if 0 <= index < leds.num_leds:
            pixels[index] = (r, g, b)
        leds.set_pixels(pixels, brightness=brightness)

    def off(self) -> None:
        self._stop_animation()
        self.resources.core.leds.clear()

    def blink(self, r: int, g: int, b: int, interval_s: float = 0.3, count: Optional[int] = None) -> None:
        self._stop_animation()

        def _run() -> None:
            leds = self.resources.core.leds
            on = True
            n = 0
            while not self._anim_stop.is_set():
                if count is not None and n >= count * 2:
                    break
                leds.set_pixels([(r, g, b) if on else (0, 0, 0)] * leds.num_leds)
                on = not on
                n += 1
                self._anim_stop.wait(interval_s)
            leds.clear()

        self._anim_thread = threading.Thread(target=_run, daemon=True)
        self._anim_thread.start()

    def chase(self, colors: List[Tuple[int, int, int]], step_interval_s: float = 0.3) -> None:
        self._stop_animation()

        def _run() -> None:
            leds = self.resources.core.leds
            i = 0
            while not self._anim_stop.is_set():
                pixels = [(0, 0, 0)] * leds.num_leds
                pixels[i % leds.num_leds] = colors[i % len(colors)]
                leds.set_pixels(pixels)
                i += 1
                self._anim_stop.wait(step_interval_s)
            leds.clear()

        self._anim_thread = threading.Thread(target=_run, daemon=True)
        self._anim_thread.start()

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "set_solid": self.set_solid,
            "set_pixel": self.set_pixel,
            "blink": self.blink,
            "chase": self.chase,
            "off": self.off,
        }


AVAILABLE_PACKAGES = [LedsPackage]
