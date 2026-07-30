"""Real hardware GPIO driver — thin wrapper over RPi.GPIO for any future
hardware beyond the matrix keyboard/LEDs."""

from __future__ import annotations

from core_os.core.drivers.base import GpioDriver


class RpiGpioDriver(GpioDriver):
    def __init__(self) -> None:
        import RPi.GPIO as GPIO

        self._gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

    def setup_output(self, pin: int) -> None:
        self._gpio.setup(pin, self._gpio.OUT)

    def setup_input(self, pin: int, pull_up: bool = True) -> None:
        pud = self._gpio.PUD_UP if pull_up else self._gpio.PUD_DOWN
        self._gpio.setup(pin, self._gpio.IN, pull_up_down=pud)

    def write(self, pin: int, high: bool) -> None:
        self._gpio.output(pin, self._gpio.HIGH if high else self._gpio.LOW)

    def read(self, pin: int) -> bool:
        return self._gpio.input(pin) == self._gpio.HIGH

    def cleanup(self) -> None:
        self._gpio.cleanup()
