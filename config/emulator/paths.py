import os

# Repo root is two directories above this file (config/emulator/paths.py)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _p(*parts):
    return os.path.join(_ROOT, *parts)

# If you need to change any particular path, you can do so here.
# This is the only place in the code where paths are defined for the emulator runtime.

PIPER_BIN              = _p("tts", "piper", "piper.exe")
MODEL_PATH             = _p("tts", "piper", "en_GB-cori-medium.onnx")
OPENJTALK_HTSVOICE_DIR = _p("tts", "openjtalk")
CACHE_DIR              = _p("tts", "piper_cache")
CONFIG_DIR             = _p("config")
FILES_DIR              = _p("files")
APPS_DIR               = _p("apps")
OVERLAY_DIR            = _p("overlays")
ICON_DIR               = _p("assets", "icons")
FONT_PATH              = _p("assets", "LanaPixel.ttf")
FONT_SMALL_PATH        = _p("assets", "pixel.ttf")
AUTOCOMPLETE_PATH      = _p("config", "autocomplete_words.txt")

# VoiceVox is an external application — set this to wherever you installed it.
VOICEVOX_BIN  = r"%USERPROFILE%\\AppData\\Local\\Programs\\VOICEVOX\\voicevox.exe"
VOICEVOX_HOST = "localhost"
VOICEVOX_PORT = 50021
