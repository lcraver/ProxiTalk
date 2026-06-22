import os

# Repo root is two directories above this file (config/paths.py)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _p(*parts):
    return os.path.join(_ROOT, *parts)

# If you need to change any particular path, you can do so here.
# This is the only place in the code where paths are defined for the runtime.

CONFIG_DIR             = _p("config")
FILES_DIR              = _p("files")
APPS_DIR               = _p("apps")
OVERLAY_DIR            = _p("overlays")
ICON_DIR               = _p("assets", "icons")
FONT_PATH              = _p("assets", "LanaPixel.ttf")
FONT_SMALL_PATH        = _p("assets", "pixel.ttf")
AUTOCOMPLETE_PATH      = _p("config", "autocomplete_words.txt")
OPENJTALK_HTSVOICE_DIR = _p("tts", "openjtalk")
CACHE_DIR              = _p("tts", "piper_cache")

# External installs — set these to wherever the binaries live on your device.
PIPER_BIN    = "/home/dietpi/piper/piper"
MODEL_PATH   = "/home/dietpi/piper/en_GB-cori-medium.onnx"
VOICEVOX_BIN = "/home/dietpi/voicevox/run"
VOICEVOX_HOST = "localhost"
VOICEVOX_PORT = 50021
