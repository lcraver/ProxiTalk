"""Real hardware LED driver — 4x SK9822 (APA102-compatible) over hardware SPI0.
Frame protocol carried over from led_test.py / hardware_test.py."""

from __future__ import annotations

from typing import List, Tuple

from core_os.core.drivers.base import LedDriver

SPI_BUS = 0
SPI_DEVICE = 0
SPI_SPEED_HZ = 1_000_000


class Sk9822LedDriver(LedDriver):
    def __init__(self, num_leds: int = 4) -> None:
        import spidev

        self.num_leds = num_leds
        self._spi = spidev.SpiDev()
        self._spi.open(SPI_BUS, SPI_DEVICE)
        self._spi.max_speed_hz = SPI_SPEED_HZ
        self._spi.mode = 0b00

    def _build_frame(self, pixels: List[Tuple[int, int, int]], brightness: int) -> List[int]:
        frame = [0x00, 0x00, 0x00, 0x00]  # start frame
        for r, g, b in pixels:
            frame += [0xE0 | brightness, b, g, r]
        frame += [0xFF] * ((self.num_leds // 2) + 1)  # end frame
        return frame

    def set_pixels(self, pixels: List[Tuple[int, int, int]], brightness: int = 8) -> None:
        self._spi.xfer2(self._build_frame(pixels, brightness))

    def clear(self) -> None:
        self.set_pixels([(0, 0, 0)] * self.num_leds)

    def stop(self) -> None:
        self.clear()
        self._spi.close()
