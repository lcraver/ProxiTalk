#!/usr/bin/env python3
"""core_os entry point for the Windows dev-machine emulator.

The ONLY file in the whole tree that imports core_os.backends.emulator_windows.
Editing anything under backends/emulator_windows/ cannot affect
entry_device.py's behavior — they share no code path except the abstract
contracts in core/drivers/base.py and the pure logic in core/scheduler.py /
core/event_bus.py.

Run from the repo root: python core_os/entry_emulator_windows.py [--dev]
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    from core_os import bootstrap
    from core_os.backends.emulator_windows import compose
    from core_os.backends.emulator_windows.config import paths

    core = compose.build_core_registry()

    watcher = None
    if "--dev" in sys.argv:
        from core_os.devtools.dev_watcher import DevWatcher

        watcher = DevWatcher(
            root=_ROOT,
            apps_dir=paths.APPS_DIR,
            backend_dir=os.path.join(_ROOT, "core_os", "backends", "emulator_windows"),
            state_dir=paths.CACHE_DIR,
        )
        watcher.start()

    bootstrap.run(core, backend_paths=paths, is_windows=True, dev_watcher=watcher)


if __name__ == "__main__":
    main()
