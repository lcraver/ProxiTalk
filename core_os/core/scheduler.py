"""Cooperative scheduler — pure logic, zero platform/hardware code.

Replaces AppManager's per-app background threads with a single loop that
calls the focused app's update() plus every running overlay's update() once
per tick. Long-running work is offloaded via run_background(), which always
delivers its callback from the next tick() call on the main thread, so
callbacks never race with app code.
"""

from __future__ import annotations

import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional


class BackgroundTask:
    """One run_background() invocation. Runs `fn` on a worker thread; the
    result/exception is delivered via on_done/on_error from the *next*
    Scheduler.tick() on the main thread."""

    def __init__(
        self,
        fn: Callable[[], Any],
        on_done: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._fn = fn
        self._on_done = on_done
        self._on_error = on_error
        self._finished = threading.Event()
        self._result: Any = None
        self._error: Optional[Exception] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "BackgroundTask":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            self._result = self._fn()
        except Exception as exc:  # noqa: BLE001 - deliver to caller, don't crash the worker
            self._error = exc
        finally:
            self._finished.set()

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    def deliver(self) -> None:
        """Call the appropriate callback. Must only be called from the main
        thread, after `finished` is True."""
        if self._error is not None:
            if self._on_error:
                try:
                    self._on_error(self._error)
                except Exception:
                    traceback.print_exc()
            else:
                print(f"[Scheduler] Unhandled background task error: {self._error}")
        else:
            if self._on_done:
                try:
                    self._on_done(self._result)
                except Exception:
                    traceback.print_exc()


class Scheduler:
    """Cooperative app scheduler: a focus stack (foreground apps, back-navigable)
    plus a set of named overlays that update alongside whichever app is focused."""

    def __init__(self, tick_hz: float = 20.0) -> None:
        self.tick_hz = tick_hz
        self._focus_stack: List[Any] = []
        self._overlay_hosts: Dict[str, Any] = {}
        self._background_tasks: List[BackgroundTask] = []
        self._tasks_lock = threading.Lock()

    # --- Focus stack (foreground apps) -----------------------------------

    def push_app(self, host: Any) -> None:
        self._focus_stack.append(host)

    def replace_app(self, host: Any) -> None:
        """Stop+pop the current top of the focus stack (if any), then push+start
        the new one. Equivalent to the old AppManager.swap_app."""
        old = self.pop_app()
        if old is not None:
            self._safe_call(old.stop)
        self.push_app(host)
        self._safe_call(host.start)

    def pop_app(self) -> Optional[Any]:
        if not self._focus_stack:
            return None
        return self._focus_stack.pop()

    def focused_app(self) -> Optional[Any]:
        return self._focus_stack[-1] if self._focus_stack else None

    # --- Overlays -----------------------------------------------------------

    def start_overlay(self, name: str, host: Any) -> None:
        self._overlay_hosts[name] = host
        self._safe_call(host.start)

    def stop_overlay(self, name: str) -> None:
        host = self._overlay_hosts.pop(name, None)
        if host is not None:
            self._safe_call(host.stop)

    def running_overlays(self) -> Dict[str, Any]:
        return dict(self._overlay_hosts)

    def is_overlay_running(self, name: str) -> bool:
        return name in self._overlay_hosts

    # --- Background work ------------------------------------------------

    def run_background(
        self,
        fn: Callable[[], Any],
        on_done: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> BackgroundTask:
        task = BackgroundTask(fn, on_done, on_error)
        with self._tasks_lock:
            self._background_tasks.append(task)
        task.start()
        return task

    def _drain_background_tasks(self) -> None:
        with self._tasks_lock:
            finished = [t for t in self._background_tasks if t.finished]
            self._background_tasks = [t for t in self._background_tasks if not t.finished]
        for task in finished:
            task.deliver()

    # --- Tick / loop ------------------------------------------------------

    @staticmethod
    def _safe_call(fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception:
            traceback.print_exc()

    def tick(self, paused: bool = False) -> None:
        """One cooperative iteration: deliver finished background-task callbacks,
        then update the focused app and every running overlay -- unless
        `paused` (see sleep/package.py's `is_sleeping`, wired through
        run_forever's `is_paused`), in which case neither runs. Background
        tasks still drain either way: those are results of work already
        started before sleep, not a per-tick app redraw, so there's nothing
        sleep-incorrect about letting one finish and deliver its callback.
        Overlays are separately stopped by sleep.enter_sleep() already, so
        this mainly matters for the FOCUSED app -- e.g. an animated GIF
        widget otherwise keeps ticking (and redrawing over "Sleeping") every
        tick regardless of sleep state, since nothing else in the loop ever
        stops calling its update()."""
        self._drain_background_tasks()
        if paused:
            return

        focused = self.focused_app()
        if focused is not None:
            self._safe_call(focused.update)

        for host in list(self._overlay_hosts.values()):
            self._safe_call(host.update)

    def run_forever(
        self,
        before_tick: Optional[Callable[[], None]] = None,
        is_paused: Optional[Callable[[], bool]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Convenience loop: calls `before_tick()` (if given — typically input
        polling/dispatch, which paces the loop by blocking up to tick_interval)
        then `tick()`, until `should_stop()` (if given) returns True -- checked
        fresh every iteration, e.g. so closing the emulator window actually
        ends the process instead of leaving this loop spinning in the
        background forever. `is_paused` (if given) is checked fresh every
        iteration and forwarded to tick() -- see its docstring."""
        interval = 1.0 / self.tick_hz if self.tick_hz > 0 else 0.05
        while should_stop is None or not should_stop():
            if before_tick is not None:
                before_tick()
            else:
                time.sleep(interval)
            self.tick(paused=bool(is_paused()) if is_paused is not None else False)

    @property
    def tick_interval(self) -> float:
        return 1.0 / self.tick_hz if self.tick_hz > 0 else 0.05
