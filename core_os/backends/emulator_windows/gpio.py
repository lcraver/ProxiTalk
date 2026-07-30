"""No-op GPIO driver — a Windows dev PC has no GPIO header."""

from __future__ import annotations

from core_os.core.drivers.base import GpioDriver


class NullGpioDriver(GpioDriver):
    def setup_output(self, pin: int) -> None:
        pass

    def setup_input(self, pin: int, pull_up: bool = True) -> None:
        pass

    def write(self, pin: int, high: bool) -> None:
        pass

    def read(self, pin: int) -> bool:
        return False

    def cleanup(self) -> None:
        pass
