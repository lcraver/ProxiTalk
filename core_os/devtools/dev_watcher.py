"""DevWatcher — hot-reload parity with the existing root-level dev_watcher.py,
adapted for core_os's structure and per-backend isolation.

Watches core_os/{core,packages,apps_runtime}/ + the repo-root apps/ tree +
bootstrap.py (shared, platform-agnostic code) plus ONLY the specific
backend_dir belonging to whichever entry point constructed this watcher — so
iterating on backends/emulator_windows/ never triggers anything while running
entry_device.py, and vice versa.

Simplified relative to V1: any watched change triggers a full process
restart (os.execv) rather than V1's scoped-app-only reload, since AppControl/
Scheduler don't exist yet at the point DevWatcher.start() is called (before
bootstrap.run()). Restarting reloads the (currently handful of apps) apps/
tree in well under a second, so this is a reasonable trade for now.

A full process restart would otherwise always land back on the launcher --
record_current_app()/consume_last_app() (see dev_state.py) persist whichever
app was in the foreground to a small state file across that os.execv, so
iterating on one specific app doesn't mean re-navigating to it after every
save (see bootstrap.run's `dev_watcher` param for the other half of this).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Dict, Optional

from core_os.devtools import dev_state


def _collect_mtimes(watch_dirs, watch_files) -> Dict[str, float]:
    mtimes: Dict[str, float] = {}
    for fpath in watch_files:
        if os.path.isfile(fpath):
            mtimes[fpath] = os.path.getmtime(fpath)
    for dpath in watch_dirs:
        if not os.path.isdir(dpath):
            continue
        for dirpath, dirnames, filenames in os.walk(dpath):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fname in filenames:
                if fname.endswith(".py") or fname == "metadata.json":
                    fpath = os.path.join(dirpath, fname)
                    mtimes[fpath] = os.path.getmtime(fpath)
    return mtimes


def _restart_process() -> None:
    print("[DevWatcher] Change detected - restarting core_os...", flush=True)
    os.execv(sys.executable, [sys.executable] + sys.argv)


class DevWatcher:
    def __init__(
        self, root: str, apps_dir: str, backend_dir: str, poll_interval: float = 1.0, state_dir: Optional[str] = None
    ) -> None:
        core_os_root = os.path.join(root, "core_os")
        self._watch_dirs = [
            os.path.join(core_os_root, "core"),
            os.path.join(core_os_root, "packages"),
            os.path.join(core_os_root, "apps_runtime"),
            apps_dir,
            backend_dir,
        ]
        self._watch_files = [os.path.join(core_os_root, "bootstrap.py")]
        self._poll_interval = poll_interval
        self._state_dir = state_dir
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="DevWatcher")
        self._mtimes: Dict[str, float] = {}

    def start(self) -> None:
        print("[DevWatcher] Started - watching for file changes", flush=True)
        self._mtimes = _collect_mtimes(self._watch_dirs, self._watch_files)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def record_current_app(self, app_name: str) -> None:
        """Called (see bootstrap.run's `on_app_changed` wiring) every time
        the foreground app changes, so whichever one was open most recently
        is what a restart triggered by a file change reopens."""
        if self._state_dir is not None:
            dev_state.save_last_app(self._state_dir, app_name)

    def consume_last_app(self) -> Optional[str]:
        """Read (and clear) the app persisted by record_current_app -- meant
        to be called exactly once, at startup, before the launcher would
        otherwise be pushed."""
        if self._state_dir is None:
            return None
        return dev_state.load_and_clear_last_app(self._state_dir)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(self._poll_interval)
            try:
                self._check()
            except Exception as exc:
                print(f"[DevWatcher] Error during check: {exc}", flush=True)

    def _check(self) -> None:
        new_mtimes = _collect_mtimes(self._watch_dirs, self._watch_files)

        for path, mtime in new_mtimes.items():
            if self._mtimes.get(path) != mtime:
                print(f"[DevWatcher] Change detected: {path}", flush=True)
                _restart_process()
                return

        for path in self._mtimes:
            if path not in new_mtimes:
                print(f"[DevWatcher] File removed: {path}", flush=True)
                _restart_process()
                return

        self._mtimes = new_mtimes
