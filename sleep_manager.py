"""Sleep controller for auto-inactivity handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


StopAudioCallable = Callable[[], None]


@dataclass
class SleepController:
    """Controls transition into and out of device sleep mode."""

    display: object
    display_queue: "queue.Queue"
    app_manager: object
    user_preferences: Optional[object]
    screen_size: tuple[int, int]
    stop_music_cb: StopAudioCallable = lambda: None
    stop_stream_cb: StopAudioCallable = lambda: None
    idle_timeout_seconds: float = 0.0
    sleeping: bool = field(default=False, init=False)
    _suspended_active_app: Optional[str] = field(default=None, init=False)
    _suspended_overlays: List[str] = field(default_factory=list, init=False)

    def set_idle_timeout(self, seconds: float) -> None:
        """Update inactivity timeout in seconds (<=0 disables auto-sleep)."""
        self.idle_timeout_seconds = max(0.0, float(seconds))

    def should_sleep(self, last_input_timestamp: float, current_time: float) -> bool:
        """Return True if idle timeout has elapsed."""
        if self.sleeping or self.idle_timeout_seconds <= 0:
            return False
        return current_time - last_input_timestamp >= self.idle_timeout_seconds

    def enter_sleep(self) -> bool:
        """Suspend running apps, audio, and blank the display."""
        if self.sleeping:
            return False

        self.sleeping = True
        self._suspended_active_app = getattr(self.app_manager, "active_app", None)
        self._suspended_overlays = [
            name
            for name in getattr(self.app_manager, "overlay_apps", [])
            if getattr(self.app_manager, "is_app_running", lambda *_: False)(name)
        ]

        # Stop every running app to free resources while sleeping
        for app_name in list(getattr(self.app_manager, "get_running_apps", lambda: [])()):
            getattr(self.app_manager, "stop_app", lambda *_: None)(app_name)

        # Silence any audio that might be playing
        try:
            self.stop_music_cb()
        except Exception as exc:
            print(f"[Sleep] Failed to stop music: {exc}")
        try:
            self.stop_stream_cb()
        except Exception as exc:
            print(f"[Sleep] Failed to stop audio stream: {exc}")

        self._set_contrast(0)
        self._show_message("Sleeping", "Press SPACE to wake")
        return True

    def exit_sleep(self) -> bool:
        """Resume previously running overlays and foreground app."""
        if not self.sleeping:
            return False

        self.sleeping = False
        self._set_contrast(255)
        self._show_message("Waking", "Loading apps...")

        # Restart overlays that were running before sleep (respect prefs)
        for overlay_name in self._suspended_overlays:
            if self.user_preferences and getattr(self.user_preferences, "is_overlay_disabled", lambda _: False)(overlay_name):
                continue
            self._start_app_if_possible(overlay_name)
        self._suspended_overlays = []

        # Resume prior active app when possible
        target_app = self._suspended_active_app or "launcher"
        if self.user_preferences and not self._app_is_loaded(target_app):
            last_launched = getattr(self.user_preferences, "get_last_launched_app", lambda: None)() or "launcher"
            target_app = last_launched

        if not self._start_app_if_possible(target_app):
            self._start_app_if_possible("launcher")

        self._suspended_active_app = None
        return True

    # --- Internal helpers -------------------------------------------------

    def _show_message(self, title: str, body: str) -> None:
        self.display_queue.put(("clear_base",))
        width, height = self.screen_size
        self.display_queue.put(("clear_overlay_area", 0, 0, width, height))
        self.display_queue.put(("set_screen", title, body))

    def _set_contrast(self, level: int) -> None:
        contrast_fn = getattr(self.display, "contrast", None)
        if callable(contrast_fn):
            try:
                contrast_fn(level)
            except Exception as exc:
                print(f"[Sleep] Failed to set contrast: {exc}")

    def _app_is_loaded(self, app_name: Optional[str]) -> bool:
        if not app_name:
            return False
        loaded = getattr(self.app_manager, "loaded_apps", {})
        return app_name in loaded

    def _start_app_if_possible(self, app_name: Optional[str]) -> bool:
        if not app_name:
            return False
        load_app = getattr(self.app_manager, "load_app", lambda *_: False)
        start_app = getattr(self.app_manager, "start_app", lambda *_a, **_k: False)

        if not self._app_is_loaded(app_name):
            if not load_app(app_name):
                return False
        return bool(start_app(app_name, update_rate_hz=20.0))