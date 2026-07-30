"""EventBus — pure logic, zero platform/hardware code.

Splits event delivery into two kinds, mirroring Tildagon's focus-routed vs
broadcast split:
  - dispatch_focused(): routed only to the focused app + running overlays
    (replaces AppManager.distribute_event). Used for input (onkeydown/onkeyup).
  - emit()/on()/on_async(): system-wide broadcasts any Package/app can
    subscribe to regardless of focus (e.g. "input_connected").
"""

from __future__ import annotations

import traceback
from typing import Any, Callable, Dict, List

from core_os.core.scheduler import Scheduler


class EventBus:
    def __init__(self, scheduler: Scheduler) -> None:
        self._scheduler = scheduler
        self._sync_handlers: Dict[str, List[Callable[..., None]]] = {}
        self._async_handlers: Dict[str, List[Callable[..., None]]] = {}

    # --- Focus-routed dispatch --------------------------------------------

    def dispatch_focused(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        focused = self._scheduler.focused_app()
        if focused is not None:
            focused.dispatch(event_name, *args, **kwargs)
        for host in self._scheduler.running_overlays().values():
            host.dispatch(event_name, *args, **kwargs)

    # --- Broadcast ----------------------------------------------------------

    def on(self, event_name: str, handler: Callable[..., None]) -> None:
        self._sync_handlers.setdefault(event_name, []).append(handler)

    def on_async(self, event_name: str, handler: Callable[..., None]) -> None:
        """Handler is invoked via Scheduler.run_background so it never blocks
        the caller of emit()."""
        self._async_handlers.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        for handler in self._sync_handlers.get(event_name, []):
            try:
                handler(*args, **kwargs)
            except Exception:
                traceback.print_exc()
        for handler in self._async_handlers.get(event_name, []):
            self._scheduler.run_background(lambda h=handler: h(*args, **kwargs))
