"""timer package — Timer/TimerManager (seconds) and FrameTimer/
FrameTimerManager (tick counts), exposed directly (no factory methods
needed, none of these touch gfx or any other package)."""

from __future__ import annotations

from typing import Any, Dict

from core_os.packages.base import Package, PackageResources
from core_os.packages.timer.frame_timer import FrameTimer, FrameTimerManager
from core_os.packages.timer.timer import Timer, TimerManager


class TimerPackage(Package):
    package_id = "timer"
    display_name = "Timer"
    priority = 10
    capability_tags = {"scheduling"}

    def initialize(self) -> None:
        pass

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "timer": Timer,
            "timer_manager": TimerManager,
            "frame_timer": FrameTimer,
            "frame_timer_manager": FrameTimerManager,
        }


AVAILABLE_PACKAGES = [TimerPackage]
