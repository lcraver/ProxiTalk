"""sleep package — idle-timeout suspend/resume, rewritten against the
Scheduler's focus stack/overlay registry instead of reaching into
AppManager's private attrs the way V1's SleepController did."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from core_os.packages.base import Package, PackageResources


class SleepPackage(Package):
    package_id = "sleep"
    display_name = "Sleep"
    priority = 50
    capability_tags = {"power"}
    core_requires = {"display"}
    package_requires = {"display_gfx"}

    def initialize(self) -> None:
        self._idle_timeout_seconds = 0.0
        self.sleeping = False
        self._suspended_overlays: List[str] = []
        self._saved_frame = None

    def set_idle_timeout(self, seconds: float) -> None:
        self._idle_timeout_seconds = max(0.0, float(seconds))

    def should_sleep(self, last_input_timestamp: float, current_time: float) -> bool:
        if self.sleeping or self._idle_timeout_seconds <= 0:
            return False
        return current_time - last_input_timestamp >= self._idle_timeout_seconds

    def is_sleeping(self) -> bool:
        return self.sleeping

    def enter_sleep(self) -> bool:
        if self.sleeping:
            return False
        self.sleeping = True

        scheduler = self.resources.core.scheduler
        self._suspended_overlays = list(scheduler.running_overlays().keys())
        for name in self._suspended_overlays:
            scheduler.stop_overlay(name)

        try:
            self.resources.core.audio_output.stop()
        except Exception as exc:
            print(f"[sleep] Failed to stop audio: {exc}")

        self.resources.core.display.contrast(0)
        gfx = self.require("display_gfx")
        # Save the exact frame that was showing so exit_sleep() can restore
        # it verbatim — this is what lets EVERY app wake up redrawn without
        # any of them needing their own redraw-on-resume logic.
        self._saved_frame = gfx.snapshot()
        gfx.clear_screen()
        gfx.draw_text("Sleeping", 4, 20, font=gfx.fonts["small"])
        gfx.draw_text("Press SPACE to wake", 4, 34, font=gfx.fonts["small"])
        return True

    def exit_sleep(self, restart_overlay_fn: Optional[Callable[[str], None]] = None) -> bool:
        if not self.sleeping:
            return False
        self.sleeping = False
        self.resources.core.display.contrast(255)
        if self._saved_frame is not None:
            self.require("display_gfx").restore(self._saved_frame)
            self._saved_frame = None
        else:
            self.require("display_gfx").clear_screen()

        if restart_overlay_fn is not None:
            for name in self._suspended_overlays:
                restart_overlay_fn(name)
        self._suspended_overlays = []
        return True

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "set_idle_timeout": self.set_idle_timeout,
            "should_sleep": self.should_sleep,
            "is_sleeping": self.is_sleeping,
            "enter_sleep": self.enter_sleep,
            "exit_sleep": self.exit_sleep,
        }


AVAILABLE_PACKAGES = [SleepPackage]
