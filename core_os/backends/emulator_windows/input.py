"""Windows dev-machine input driver — wraps keyboard_manager.KeyboardManager's
Windows-hook path behind the InputDriver contract."""

from __future__ import annotations

from typing import Callable, List, Optional

from core_os.backends.emulator_windows.keyboard_manager import KeyboardManager

from core_os.core.drivers.base import KEY_DOWN, KEY_UP, InputDriver, InputEvent


class EmulatorInputDriver(InputDriver):
    def __init__(
        self,
        win_keycode_map: Optional[dict] = None,
        on_f10_pressed: Optional[Callable[[], None]] = None,
    ) -> None:
        self._manager = KeyboardManager(is_windows=True, win_keycode_map=win_keycode_map)
        self._on_f10_pressed = on_f10_pressed

    def set_f10_handler(self, handler: Optional[Callable[[], None]]) -> None:
        self._on_f10_pressed = handler

    def inject_key(self, keycode: str, is_down: bool) -> None:
        """Feeds a synthetic key press into the same queue real presses use —
        wired to the debug overlay's clickable device map (see compose.py)."""
        self._manager.inject(keycode, KEY_DOWN if is_down else KEY_UP)

    def start(self) -> None:
        self._manager.start()

    def stop(self) -> None:
        self._manager.stop()

    def is_ready(self) -> bool:
        return self._manager.is_ready()

    def poll(self, timeout: float = 0.0) -> List[InputEvent]:
        events: List[InputEvent] = []
        first = self._manager.get_event(timeout=timeout)
        if first is not None:
            self._append_event(events, first)
        while True:
            nxt = self._manager.get_event(timeout=0)
            if nxt is None:
                break
            self._append_event(events, nxt)
        return events

    def _append_event(self, events: List[InputEvent], ev) -> None:
        if ev.kind == "key" and ev.keycode == "KEY_F10":
            if ev.keystate == KEY_DOWN and self._on_f10_pressed is not None:
                self._on_f10_pressed()
            return
        events.append(self._convert(ev))

    @staticmethod
    def _convert(ev) -> InputEvent:
        return InputEvent(kind=ev.kind, keycode=ev.keycode, keystate=ev.keystate, data=ev.data, timestamp=ev.timestamp)
