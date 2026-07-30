"""Real Raspberry Pi paths for the device_pi backend.

Self-contained: core_os owns these values directly instead of importing V1's
config/paths.py. Font/app/overlay paths point at core_os's own assets and
apps/ tree; TTS binary paths are genuinely platform-specific installs that
happen to live at the same filesystem locations V1 uses on this same device.
"""

from __future__ import annotations

import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def _p(*parts: str) -> str:
    return os.path.join(_ROOT, *parts)


# External installs — set these to wherever the binaries live on the device.
PIPER_BIN = "/home/dietpi/piper/piper"
MODEL_PATH = "/home/dietpi/piper/en_GB-cori-medium.onnx"
OPENJTALK_HTSVOICE_DIR = _p("tts", "openjtalk")

# piper-plus's ONNX model is a cross-platform format loaded in-process via the
# piper Python package, so unlike PIPER_BIN/MODEL_PATH (which need a
# platform-specific binary) the SAME repo-committed model file works for both
# this backend and the Windows emulator, no per-platform install step needed.
PIPER_PLUS_MODEL = _p("tts", "piper_plus", "ja_JP-tsukuyomi-chan-medium.onnx")

CACHE_DIR = _p("tts", "piper_cache")
CONFIG_DIR = _p("config")
FILES_DIR = _p("files")
ICON_DIR = _p("assets")
# core_os uses Misaki Gothic for all rendering (Latin + Japanese in one font).
FONT_PATH = _p("assets", "misaki_gothic.ttf")
FONT_SMALL_PATH = _p("assets", "misaki_gothic.ttf")
AUTOCOMPLETE_PATH = _p("config", "autocomplete_words.txt")

# core_os apps live at the repo-root apps/ tree (legacy V1 apps were moved
# aside to old_apps/, freeing this name up for core_os).
APPS_DIR = _p("apps")
OVERLAY_DIR = _p("core_os", "overlays_v2")
