"""CoreRegistry — a plain dependency-injection container.

It holds whatever driver instances it's handed and constructs the Scheduler/
EventBus. It never constructs, selects, or knows where its drivers came from —
that decision belongs entirely to a backend's compose.py + the entry point that
calls it. This is what keeps `core/` free of any platform-detection code.
"""

from __future__ import annotations

from core_os.core.drivers.base import (
    AudioOutputDriver,
    DisplayDriver,
    GpioDriver,
    InputDriver,
    LedDriver,
)
from core_os.core.event_bus import EventBus
from core_os.core.scheduler import Scheduler


class CoreRegistry:
    def __init__(
        self,
        display: DisplayDriver,
        input: InputDriver,
        audio_output: AudioOutputDriver,
        leds: LedDriver,
        gpio: GpioDriver,
        tick_hz: float = 20.0,
    ) -> None:
        self.display = display
        self.input = input
        self.audio_output = audio_output
        self.leds = leds
        self.gpio = gpio
        self.scheduler = Scheduler(tick_hz=tick_hz)
        self.event_bus = EventBus(self.scheduler)

    def start(self) -> None:
        self.input.start()

    def shutdown(self) -> None:
        for driver in (self.display, self.input, self.audio_output, self.leds):
            try:
                driver.stop()
            except Exception as exc:
                print(f"[CoreRegistry] Error stopping driver {driver!r}: {exc}")
        try:
            self.gpio.cleanup()
        except Exception as exc:
            print(f"[CoreRegistry] Error cleaning up GPIO: {exc}")
