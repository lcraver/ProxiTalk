"""Composition root for the Windows emulator backend. The ONLY function that
knows how to build a full CoreRegistry for this environment."""

from __future__ import annotations

import os

from core_os.backends.emulator_windows.audio_output import PygameAudioOutputDriver
from core_os.backends.emulator_windows.config import paths
from core_os.backends.emulator_windows.display import EmulatorDisplayDriver
from core_os.backends.emulator_windows.gpio import NullGpioDriver
from core_os.backends.emulator_windows.input import EmulatorInputDriver
from core_os.backends.emulator_windows.leds import NullLedDriver
from core_os.backends.emulator_windows.win_keycodes import WIN_TO_LINUX_KEYCODE
from core_os.core.registry import CoreRegistry

DEFAULT_TICK_HZ = 20.0
FAST_TICK_HZ = 60.0


def build_core_registry(width: int = 248, height: int = 120) -> CoreRegistry:
    input_driver = EmulatorInputDriver(win_keycode_map=WIN_TO_LINUX_KEYCODE)
    debug_overlay_settings_path = os.path.join(paths.CONFIG_DIR, "emulator_debug_overlay.json")
    core = CoreRegistry(
        display=EmulatorDisplayDriver(
            width=width, height=height, icon_dir=paths.ICON_DIR, settings_path=debug_overlay_settings_path
        ),
        input=input_driver,
        audio_output=PygameAudioOutputDriver(),
        leds=NullLedDriver(),
        gpio=NullGpioDriver(),
        tick_hz=DEFAULT_TICK_HZ,
    )

    def enable_fast_mode() -> None:
        if core.scheduler.tick_hz >= FAST_TICK_HZ:
            return
        core.scheduler.tick_hz = FAST_TICK_HZ
        print(f"[Emulator] F10 pressed: scheduler set to {int(FAST_TICK_HZ)} FPS")

    input_driver.set_f10_handler(enable_fast_mode)
    core.display.set_key_event_callback(input_driver.inject_key)
    return core
