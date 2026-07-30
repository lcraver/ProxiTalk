"""Composition root for the real Raspberry Pi backend. The ONLY function that
knows how to build a full CoreRegistry for this environment."""

from __future__ import annotations

from typing import Optional

from core_os.backends.device_pi.audio_output import AplayAudioOutputDriver
from core_os.backends.device_pi.display import LumaDisplayDriver
from core_os.backends.device_pi.gpio import RpiGpioDriver
from core_os.backends.device_pi.input import MatrixInputDriver
from core_os.backends.device_pi.leds import Sk9822LedDriver
from core_os.core.drivers.base import DisplayDriver
from core_os.core.registry import CoreRegistry


def build_core_registry(display: Optional[DisplayDriver] = None) -> CoreRegistry:
    # `display`, if given, is a driver already opened earlier in boot (e.g.
    # by entry_device.py to show the update-check screen before the rest of
    # the app stack exists) -- reused here instead of opening a second
    # ssd1309/I2C handle on the same physical device.
    return CoreRegistry(
        display=display if display is not None else LumaDisplayDriver(),
        input=MatrixInputDriver(),
        audio_output=AplayAudioOutputDriver(),
        leds=Sk9822LedDriver(),
        gpio=RpiGpioDriver(),
    )
