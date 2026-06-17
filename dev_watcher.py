import os
import sys
import time
import threading


# Root-level .py files and packages considered part of the core OS.
# A change to any of these triggers a full process restart.
_CORE_FILES = {
    "proxitalk.py",
    "app_manager.py",
    "interfaces.py",
    "emulator_display.py",
    "keyboard_manager.py",
    "audio_manager.py",
    "sleep_manager.py",
    "tts_engine_manager.py",
}
_CORE_DIRS = {"config", "utils", "tts_engines", "tts"}


def _collect_mtimes(root: str, apps_dir: str):
    """
    Return two dicts of {path: mtime}:
      core_mtimes  – root-level core files + config/utils packages
      app_mtimes   – {app_name: {path: mtime}}
    """
    core: dict[str, float] = {}
    apps: dict[str, dict[str, float]] = {}

    # Core root files
    for fname in _CORE_FILES:
        fpath = os.path.join(root, fname)
        if os.path.isfile(fpath):
            core[fpath] = os.path.getmtime(fpath)

    # Core package directories
    for dirname in _CORE_DIRS:
        dpath = os.path.join(root, dirname)
        if not os.path.isdir(dpath):
            continue
        for dirpath, _, filenames in os.walk(dpath):
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = os.path.join(dirpath, fname)
                    core[fpath] = os.path.getmtime(fpath)

    # App directories
    if os.path.isdir(apps_dir):
        for dirpath, dirnames, filenames in os.walk(apps_dir):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(dirpath, fname)
                # Determine which app this file belongs to by finding the
                # first-level subdirectory under apps_dir.
                rel = os.path.relpath(fpath, apps_dir)
                parts = rel.split(os.sep)
                app_name = parts[0]
                apps.setdefault(app_name, {})[fpath] = os.path.getmtime(fpath)

    return core, apps


def _restart_process():
    print("[DevWatcher] Core file changed — restarting ProxiTalk...", flush=True)
    # Replace this process with a fresh copy of itself.
    os.execv(sys.executable, [sys.executable] + sys.argv)


class DevWatcher:
    """
    Background thread that watches source files for changes.

    - A change inside an app directory reloads just that app via app_manager.
    - A change to a core OS file restarts the whole process.
    """

    def __init__(self, root: str, apps_dir: str, app_manager, poll_interval: float = 1.0):
        self._root = root
        self._apps_dir = apps_dir
        self._app_manager = app_manager
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="DevWatcher"
        )

    def start(self):
        print("[DevWatcher] Started — watching for file changes", flush=True)
        self._core_mtimes, self._app_mtimes = _collect_mtimes(
            self._root, self._apps_dir
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        while not self._stop_event.is_set():
            time.sleep(self._poll_interval)
            try:
                self._check()
            except Exception as exc:
                print(f"[DevWatcher] Error during check: {exc}", flush=True)

    def _check(self):
        new_core, new_apps = _collect_mtimes(self._root, self._apps_dir)

        # Check core files first — any change triggers a full restart.
        for path, mtime in new_core.items():
            old = self._core_mtimes.get(path)
            if old is None or mtime != old:
                print(f"[DevWatcher] Core change detected: {path}", flush=True)
                _restart_process()
                return  # unreachable after execv, but be explicit

        # Check for new core files (e.g. someone added a module).
        for path in self._core_mtimes:
            if path not in new_core:
                print(f"[DevWatcher] Core file removed: {path}", flush=True)
                _restart_process()
                return

        self._core_mtimes = new_core

        # Check app files — reload the affected app only.
        changed_apps: set[str] = set()

        for app_name, file_map in new_apps.items():
            old_file_map = self._app_mtimes.get(app_name, {})
            for path, mtime in file_map.items():
                if mtime != old_file_map.get(path):
                    changed_apps.add(app_name)
            # Also catch deleted files within the app.
            for path in old_file_map:
                if path not in file_map:
                    changed_apps.add(app_name)

        # Catch entirely removed app directories.
        for app_name in self._app_mtimes:
            if app_name not in new_apps:
                changed_apps.add(app_name)

        self._app_mtimes = new_apps

        for app_name in changed_apps:
            print(
                f"[DevWatcher] App change detected: {app_name} — reloading...",
                flush=True,
            )
            try:
                # Determine the update rate from the running thread if available.
                hz = 20.0
                self._app_manager.reload_app(app_name, update_rate_hz=hz)
                print(f"[DevWatcher] Reloaded app: {app_name}", flush=True)
            except Exception as exc:
                print(f"[DevWatcher] Failed to reload '{app_name}': {exc}", flush=True)
