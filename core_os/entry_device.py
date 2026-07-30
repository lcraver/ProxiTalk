#!/usr/bin/env python3
"""core_os entry point for the real Raspberry Pi hardware.

The ONLY file in the whole tree that imports core_os.backends.device_pi.
Editing anything under backends/device_pi/ cannot affect
entry_emulator_windows.py's behavior — they share no code path except the
abstract contracts in core/drivers/base.py and the pure logic in
core/scheduler.py / core/event_bus.py.

Run on the Pi (over SSH): python3 core_os/entry_device.py [--dev]
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    from core_os.backends.device_pi.config import paths
    from core_os.shared_config import init as init_shared_config
    from core_os.updater import updater

    # Opened here (before compose builds the rest of the app stack) purely
    # to show update progress on-screen. If this fails (e.g. no I2C device
    # attached, driver import error) update checking still runs, just
    # without a UI -- a screen we can't open must not block booting.
    early_display = None
    ui = None
    if "--dev" not in sys.argv:
        try:
            from core_os.backends.device_pi.display import LumaDisplayDriver
            from core_os.updater.updater_ui import UpdaterUI

            early_display = LumaDisplayDriver()
            ui = UpdaterUI(early_display, paths.FONT_PATH, paths.FONT_SMALL_PATH)
        except Exception as exc:
            print(f"[updater] Could not open display for update UI: {exc}")

    # Runs before the rest of the hardware stack is built -- if a newer
    # release gets installed, run_auto_update() reboots the device itself
    # and this process should never fall through to booting with now-stale
    # module state. --dev is excluded so a dev checkout never gets
    # overwritten by a release mid-session.
    if "--dev" not in sys.argv:
        shared_config = init_shared_config(os.path.join(paths.CONFIG_DIR, "shared_config.json"))
        if updater.run_auto_update(_ROOT, enabled=shared_config.get("auto_update_enabled", True), ui=ui):
            return

    from core_os import bootstrap
    from core_os.backends.device_pi import compose

    core = compose.build_core_registry(display=early_display)

    watcher = None
    if "--dev" in sys.argv:
        from core_os.devtools.dev_watcher import DevWatcher

        watcher = DevWatcher(
            root=_ROOT,
            apps_dir=paths.APPS_DIR,
            backend_dir=os.path.join(_ROOT, "core_os", "backends", "device_pi"),
            state_dir=paths.CACHE_DIR,
        )
        watcher.start()

    bootstrap.run(core, backend_paths=paths, is_windows=False, dev_watcher=watcher)


if __name__ == "__main__":
    main()
