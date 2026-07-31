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

    def is_running(self) -> bool:
        """False once the display has been closed from the outside (e.g. the
        emulator window's close button/File > Quit) and the whole process
        should shut down. Real hardware has no such concept, so the default
        is always-True -- only backends with a closable window override it."""
        return True


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


class PCMStream(ABC):
    """A long-lived raw-PCM output stream, for continuous/real-time audio
    (see packages/synth/player.py's SynthEngine) — distinct from play_pcm()
    below, which commits to ONE finite buffer per call and blocks the
    calling thread for its entire duration. write() should be treated as
    "emit this chunk" only: callers are responsible for their OWN pacing
    (see SynthEngine's self-timed mixer loop) rather than relying on
    write() to block/backpressure them, since whether it blocks at all
    differs by backend (e.g. a Pi's aplay stdin pipe vs. Windows' pygame
    mixer channel) and leaning on that difference would give the two
    backends different failure modes instead of actual parity."""

    @abstractmethod
    def write(self, pcm_bytes: bytes) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...


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

    @abstractmethod
    def open_pcm_stream(self, sample_rate: int) -> PCMStream:
        """Opens a new long-lived PCMStream for continuous playback. Caller
        owns the returned stream's lifetime (must call .close() when done)."""

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
