"""Windows dev-machine paths for the emulator_windows backend.

Self-contained: core_os owns these values directly instead of importing V1's
config/emulator/paths.py.
"""

from __future__ import annotations

import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def _p(*parts: str) -> str:
    return os.path.join(_ROOT, *parts)


PIPER_BIN = _p("tts", "piper", "piper.exe")
MODEL_PATH = _p("tts", "piper", "en_GB-cori-medium.onnx")
OPENJTALK_HTSVOICE_DIR = _p("tts", "openjtalk")
CACHE_DIR = _p("tts", "piper_cache")
CONFIG_DIR = _p("config")
FILES_DIR = _p("files")
ICON_DIR = _p("assets")
# core_os uses Misaki Gothic for all rendering (Latin + Japanese in one font).
FONT_PATH = _p("assets", "misaki_gothic.ttf")
FONT_SMALL_PATH = _p("assets", "misaki_gothic.ttf")
AUTOCOMPLETE_PATH = _p("config", "autocomplete_words.txt")

# piper-plus has no V1 equivalent (core_os-only engine) — see device_pi's
# paths.py for why the same repo-committed .onnx works on both backends.
PIPER_PLUS_MODEL = _p("tts", "piper_plus", "ja_JP-tsukuyomi-chan-medium.onnx")

# core_os apps live at the repo-root apps/ tree (legacy V1 apps were moved
# aside to old_apps/, freeing this name up for core_os).
APPS_DIR = _p("apps")
OVERLAY_DIR = _p("core_os", "overlays_v2")
