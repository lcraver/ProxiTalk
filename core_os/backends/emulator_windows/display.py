"""Windows dev-machine display driver — ports emulator_display.EmulatedDisplay
(pygame-backed) behind the DisplayDriver contract."""

from __future__ import annotations

from core_os.backends.emulator_windows.emulator_display import EmulatedDisplay

from core_os.core.drivers.base import DisplayDriver

# Physical panel is 250x122 (hardware-fixed, can't grow) but only 248x120 is
# addressable content — a 1px border on all four sides, centered. Passed to
# EmulatedDisplay as physical_size so the border stays permanently blank
# while apps size themselves to 248x120, matching the real device exactly.
PANEL_WIDTH = 250
PANEL_HEIGHT = 122


class EmulatorDisplayDriver(DisplayDriver):
    def __init__(
        self,
        width: int = 248,
        height: int = 120,
        icon_dir: str = "../../../assets",
        scale: int = 4,
        settings_path: str = "",
    ) -> None:
        self.width = width
        self.height = height
        self._impl = EmulatedDisplay(
            width, height, icon_dir, scale=scale, physical_size=(PANEL_WIDTH, PANEL_HEIGHT),
            settings_path=settings_path or None,
        )

    def fill(self, color: int) -> None:
        self._impl.fill(color)

    def image(self, img) -> None:
        self._impl.image(img)

    def show(self) -> None:
        self._impl.show()

    def contrast(self, level: int) -> None:
        self._impl.contrast(level)

    def invert(self, flag: bool) -> None:
        self._impl.invert(flag)

    def stop(self) -> None:
        self._impl.stop()

    def is_window_focused(self) -> bool:
        fn = getattr(self._impl, "is_window_focused", None)
        return fn() if fn else True

    def add_debug_region(self, x: int, y: int, width: int, height: int) -> None:
        fn = getattr(self._impl, "add_debug_region", None)
        if fn:
            fn(x, y, width, height)

    def set_key_event_callback(self, callback) -> None:
        """Wired by compose.py so clicking a key on the debug overlay's device
        map injects a real key event, same as pressing it for real."""
        fn = getattr(self._impl, "set_key_event_callback", None)
        if fn:
            fn(callback)
