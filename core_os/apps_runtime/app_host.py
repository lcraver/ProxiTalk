"""AppHost — wraps one loaded AppBase instance + its manifest + scoped
context. Collapses V1's three parallel dicts (loaded_apps/running_apps/
app_cursor_preferences) into one object per app, and provides the
dispatch()/update() shape the Scheduler and EventBus call by duck typing
(neither imports this module — see core/scheduler.py, core/event_bus.py)."""

from __future__ import annotations

import traceback
from typing import Any


class AppHost:
    def __init__(self, name: str, app_instance: Any, manifest: Any, scoped_context: Any) -> None:
        self.name = name
        self.app_instance = app_instance
        self.manifest = manifest
        self.scoped_context = scoped_context
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        try:
            self.app_instance.start()
        except Exception:
            print(f"[AppHost] Exception starting '{self.name}':")
            traceback.print_exc()

    def update(self) -> None:
        try:
            self.app_instance.update()
        except Exception:
            print(f"[AppHost] Exception in '{self.name}'.update():")
            traceback.print_exc()

    def dispatch(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        handler = getattr(self.app_instance, event_name, None)
        if handler is None:
            return
        try:
            handler(*args, **kwargs)
        except Exception:
            print(f"[AppHost] Exception in '{self.name}'.{event_name}():")
            traceback.print_exc()

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        try:
            self.app_instance.stop()
        except Exception:
            print(f"[AppHost] Exception stopping '{self.name}':")
            traceback.print_exc()
