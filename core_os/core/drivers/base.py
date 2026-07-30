"""Driver contracts for the Core layer.

These are abstract interfaces only — no implementation, no platform knowledge.
Concrete drivers (real hardware or emulated) live in core_os/backends/*, each of
which imports only this module, never anything above `core/` in the tree.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


class DisplayDriver(ABC):
    """A monochrome (1-bit) display surface."""

    width: int
    height: int

    @abstractmethod
    def fill(self, color: int) -> None:
        """Fill the entire display with 0 (off) or a nonzero value (on)."""

    @abstractmethod
    def image(self, img) -> None:
        """Blit a PIL Image (mode '1') to the display."""

    @abstractmethod
    def show(self) -> None:
        """Flush whatever was last set via image()/fill() to the physical panel."""

    @abstractmethod
    def contrast(self, level: int) -> None:
        """Set display contrast/brightness, 0-255."""

    def invert(self, flag: bool) -> None:
        """Optional: invert display colors. Default no-op."""

    @abstractmethod
    def stop(self) -> None:
        """Release any resources (threads, device handles) held by this driver."""


@dataclass
class InputEvent:
    """A single input event: a keypress/release, or a connection status change."""

    kind: str  # "key" or "status"
    keycode: Optional[str] = None
    keystate: Optional[int] = None
    data: Optional[str] = None
    timestamp: float = 0.0


KEY_DOWN = 1
KEY_UP = 0


class InputDriver(ABC):
    """Produces InputEvents. May run its own background reader thread internally —
    only app-level dispatch (via the Scheduler) is required to stay cooperative,
    not driver internals."""

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def poll(self, timeout: float = 0.0) -> List[InputEvent]:
        """Return any InputEvents queued since the last call, waiting up to
        `timeout` seconds if none are immediately available."""

    def is_ready(self) -> bool:
        return True


class AudioOutputDriver(ABC):
    """Plays back audio. Does not know about sfx/music/streaming semantics —
    that's the `audio` Package's job."""

    @abstractmethod
    def play_pcm(self, pcm_bytes: bytes, sample_rate: int, blocking: bool = False) -> None:
        ...

    @abstractmethod
    def play_file(self, path: str, blocking: bool = False) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    def set_volume(self, volume: float) -> None:
        """Optional: 0.0-1.0. Default no-op."""


class LedDriver(ABC):
    """Controls a strip of RGB LEDs."""

    num_leds: int = 0

    @abstractmethod
    def set_pixels(self, pixels: List[tuple], brightness: int = 8) -> None:
        """pixels: list of (r, g, b) tuples, length == num_leds."""

    @abstractmethod
    def clear(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...


class GpioDriver(ABC):
    """Generic GPIO access, for future hardware beyond the matrix/LEDs."""

    @abstractmethod
    def setup_output(self, pin: int) -> None:
        ...

    @abstractmethod
    def setup_input(self, pin: int, pull_up: bool = True) -> None:
        ...

    @abstractmethod
    def write(self, pin: int, high: bool) -> None:
        ...

    @abstractmethod
    def read(self, pin: int) -> bool:
        ...

    @abstractmethod
    def cleanup(self) -> None:
        ...
