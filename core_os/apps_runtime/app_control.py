"""AppControl — the narrow façade apps receive as context["app_control"],
replacing V1's context["app_manager"] so apps can't reach into scheduler
internals directly. Built on top of AppLoader + Scheduler."""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from core_os.apps_runtime.app_loader import AppLoader
from core_os.core.scheduler import Scheduler


class AppControl:
    def __init__(
        self, loader: AppLoader, scheduler: Scheduler, on_app_changed: Optional[Callable[[str], None]] = None
    ) -> None:
        self._loader = loader
        self._scheduler = scheduler
        # Only ever set by bootstrap.run when a DevWatcher exists (see its
        # `dev_watcher` param) -- lets --dev restarts reopen whatever app
        # was in the foreground instead of always the launcher. A no-op in
        # every other build/run since nothing wires it up otherwise.
        self._on_app_changed = on_app_changed

    def swap_app(self, from_app: str, to_app: str) -> bool:
        try:
            host = self._loader.load_app_instance(to_app)
        except Exception as exc:
            print(f"[AppControl] Failed to load '{to_app}': {exc}")
            return False
        self._scheduler.replace_app(host)
        if self._on_app_changed is not None:
            self._on_app_changed(to_app)
        return True

    def swap_app_async(self, from_app: str, to_app: str, delay: float = 0.0) -> None:
        def _work() -> bool:
            if delay:
                time.sleep(delay)
            return self.swap_app(from_app, to_app)

        self._scheduler.run_background(_work)

    def start_overlay(self, name: str) -> bool:
        if self._scheduler.is_overlay_running(name):
            return True
        try:
            host = self._loader.load_app_instance(name)
        except Exception as exc:
            print(f"[AppControl] Failed to load overlay '{name}': {exc}")
            return False
        self._scheduler.start_overlay(name, host)
        return True

    def stop_overlay(self, name: str) -> None:
        self._scheduler.stop_overlay(name)

    def is_overlay_running(self, name: str) -> bool:
        return self._scheduler.is_overlay_running(name)

    def list_overlays(self) -> List[str]:
        return list(self._scheduler.running_overlays().keys())

    def get_app_instance(self, name: str):
        focused = self._scheduler.focused_app()
        if focused is not None and getattr(focused, "name", None) == name:
            return focused.app_instance
        overlays = self._scheduler.running_overlays()
        host = overlays.get(name)
        return host.app_instance if host else None
