"""bootstrap.py — pure, platform-agnostic composition helper.

Given an already-built CoreRegistry (constructed by a backend's compose.py)
and that backend's config.paths module, this builds the PackageRegistry,
AppLoader, AppControl, loads+pushes the launcher, and runs the scheduler
loop. Knows nothing about which backend produced the CoreRegistry it's
handed — every entry point calls the exact same run() function.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from core_os.apps_runtime.app_control import AppControl
from core_os.apps_runtime.app_loader import AppLoader
from core_os.core.drivers.base import KEY_DOWN
from core_os.core.registry import CoreRegistry
from core_os.packages.base import PackageResources
from core_os.packages.registry import PackageRegistry
from core_os.shared_config import init as init_shared_config

if TYPE_CHECKING:
    from core_os.devtools.dev_watcher import DevWatcher


def run(
    core: CoreRegistry,
    backend_paths,
    is_windows: bool,
    start_app: str = "launcher",
    dev_watcher: Optional[DevWatcher] = None,
) -> None:
    """dev_watcher is only passed by entry points running with --dev (see
    devtools/dev_watcher.py); left as None, resumed-app tracking and its
    on_app_changed wiring below are simply skipped, restarts always land back
    on `start_app`."""
    shared_config = init_shared_config(os.path.join(backend_paths.CONFIG_DIR, "shared_config.json"))

    japanese_autocomplete = os.path.join(
        os.path.dirname(backend_paths.AUTOCOMPLETE_PATH), "autocomplete_words_japanese.txt"
    )

    resources = PackageResources(
        is_windows=is_windows,
        core=core,
        config_dir=backend_paths.CONFIG_DIR,
        files_dir=backend_paths.FILES_DIR,
        cache_dir=backend_paths.CACHE_DIR,
        shared_config=shared_config,
        paths={
            "font_path": backend_paths.FONT_PATH,
            "font_small_path": backend_paths.FONT_SMALL_PATH,
            "apps_dir": backend_paths.APPS_DIR,
            "overlay_dir": backend_paths.OVERLAY_DIR,
            "autocomplete_path": backend_paths.AUTOCOMPLETE_PATH,
            "autocomplete_japanese_path": japanese_autocomplete,
            # tts_engines/*.py each read their own key(s) from EngineResources.paths
            # (see piper_engine.py/piper_plus_engine.py/pyopenjtalk_engine.py) —
            # TTSPackage passes this same dict straight through unmodified.
            "piper_bin": getattr(backend_paths, "PIPER_BIN", None),
            "piper_model": getattr(backend_paths, "MODEL_PATH", None),
            "piper_plus_model": getattr(backend_paths, "PIPER_PLUS_MODEL", None),
            "openjtalk_htsvoice_dir": getattr(backend_paths, "OPENJTALK_HTSVOICE_DIR", None),
        },
    )

    packages = PackageRegistry(resources)

    universal_fields: Dict[str, Any] = {
        "screen_width": core.display.width,
        "screen_height": core.display.height,
    }

    loader = AppLoader(apps_dir=backend_paths.APPS_DIR, package_registry=packages, universal_fields=universal_fields)
    on_app_changed = dev_watcher.record_current_app if dev_watcher is not None else None
    app_control = AppControl(loader, core.scheduler, on_app_changed=on_app_changed)
    universal_fields["app_control"] = app_control

    sleep_pkg = packages.get_package("sleep")
    if sleep_pkg is not None:
        sleep_pkg.set_idle_timeout(float(shared_config.get("auto_sleep_minutes", 5.0)) * 60.0)

    core.start()

    # A DevWatcher-triggered restart (os.execv, see dev_watcher.py) re-runs
    # this same entry point from scratch -- resuming whatever app was last
    # in the foreground (see AppControl's on_app_changed above) instead of
    # always restarting at the launcher is what makes `--dev` iteration on a
    # specific app not require re-navigating to it after every save.
    if dev_watcher is not None:
        resumed_app = dev_watcher.consume_last_app()
        if resumed_app is not None:
            start_app = resumed_app

    try:
        launcher_host = loader.load_app_instance(start_app)
    except Exception as exc:
        # A resumed app name (see above) can go stale -- renamed/deleted
        # while --dev was running -- and that shouldn't be able to wedge
        # every subsequent restart into a crash loop.
        if start_app != "launcher":
            print(f"[bootstrap] Failed to resume '{start_app}', falling back to launcher: {exc}")
            launcher_host = loader.load_app_instance("launcher")
        else:
            raise
    core.scheduler.push_app(launcher_host)
    launcher_host.start()

    last_input_time = time.monotonic()

    # Shift resolution happens HERE, centrally, before any event reaches a
    # package or app — mirrors proxitalk.py's apply_shift_mapping() in its
    # main loop. Raw keycodes only identify the physical key (e.g. both '/'
    # and shift+'/' report KEY_SLASH; the shift modifier is a separate,
    # simultaneous key event), so without tracking shift state here and
    # remapping via shift_key_map (KEY_SLASH -> KEY_QUESTION, etc.), apps
    # would never see the shifted variant no matter how key_map.py is set
    # up on the receiving end.
    input_pkg = packages.get_package("input")
    _shift_keys = {"KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"}
    _shift_held: set = set()

    # On the Windows emulator, keyboard_manager.KeyboardManager installs a
    # GLOBAL OS-level hook (via the `keyboard` library) that captures every
    # keystroke system-wide, regardless of which window is focused. Without
    # this check, typing in an unrelated window would still get delivered to
    # the focused app here. Real hardware drivers have no such concept, so
    # is_window_focused is duck-typed and optional (mirrors proxitalk.py's
    # `focus_check = getattr(disp, "is_window_focused", None)`).
    focus_check = getattr(core.display, "is_window_focused", None)

    def _poll_and_dispatch() -> None:
        nonlocal last_input_time
        for ev in core.input.poll(timeout=core.scheduler.tick_interval):
            if ev.kind == "key":
                if focus_check is not None and not focus_check():
                    continue

                last_input_time = time.monotonic()
                if sleep_pkg is not None and sleep_pkg.is_sleeping():
                    sleep_pkg.exit_sleep(restart_overlay_fn=app_control.start_overlay)
                    continue

                if ev.keycode in _shift_keys:
                    if ev.keystate == KEY_DOWN:
                        _shift_held.add(ev.keycode)
                    else:
                        _shift_held.discard(ev.keycode)

                keycode = ev.keycode
                if input_pkg is not None:
                    keycode = input_pkg.apply_shift_mapping(keycode, bool(_shift_held))

                event_name = "onkeydown" if ev.keystate == KEY_DOWN else "onkeyup"
                core.event_bus.dispatch_focused(event_name, keycode)
            elif ev.kind == "status":
                core.event_bus.emit(f"input_{ev.data}")

        if sleep_pkg is not None and sleep_pkg.should_sleep(last_input_time, time.monotonic()):
            sleep_pkg.enter_sleep()

    try:
        is_paused = sleep_pkg.is_sleeping if sleep_pkg is not None else None
        core.scheduler.run_forever(before_tick=_poll_and_dispatch, is_paused=is_paused)
    finally:
        packages.shutdown_all()
        core.shutdown()
