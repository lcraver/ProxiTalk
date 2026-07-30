"""language package — system-wide language setting (English/Japanese).

Persisted via shared_config's "language" key. Owns:
  - t(key): translated UI strings, loaded from each app's own
    `strings.json` (see _load_strings) rather than a central table, so an
    app dev adds/edits translations inside their own app folder and never
    has to touch this package.
  - set_language(lang): persists the choice AND auto-switches the active
    TTS engine (openjtalk for Japanese, piper for English, with voicevox as
    a fallback) via the tts package, so "system-wide" covers both UI text
    and speech, not just one or the other.
  - romaji_preview(buffer)/to_speech_text(text): live, incremental romaji
    -> hiragana conversion (romaji_ime.py — a real mora-by-mora parser,
    not a keyword heuristic), so typed text converts to kana as you type,
    not just once at the moment you press Enter to speak.

Known limitation: this is phonetic conversion, not a dictionary — a
handful of words have historical/grammatical spellings a pure phonetic
parser can't know (e.g. こんにちは is written with は, pronounced "wa" as a
grammatical exception; romaji "konnichiwa" phonetically parses to わ). Also
not a true kanji-conversion IME with candidate selection — that's a much
larger, separate feature.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from core_os.packages.base import Package, PackageResources
from core_os.packages.language.romaji_ime import convert_romaji, convert_romaji_full

_STRINGS_FILENAME = "strings.json"


def _load_strings(apps_dir: Optional[str]) -> Dict[str, Dict[str, str]]:
    """Merge every apps/<app>/strings.json into one lookup table. Each
    file owns whatever dotted keys its app uses (conventionally
    "<app_name>.<thing>", plus "apps.<app_name>" for the app's own display
    name) — this package never needs to know which apps exist or what
    strings they define."""
    strings: Dict[str, Dict[str, str]] = {}
    if not apps_dir or not os.path.isdir(apps_dir):
        return strings
    for entry in sorted(os.listdir(apps_dir)):
        strings_path = os.path.join(apps_dir, entry, _STRINGS_FILENAME)
        if not os.path.isfile(strings_path):
            continue
        try:
            with open(strings_path, "r", encoding="utf-8") as f:
                app_strings = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[language] Failed to load '{strings_path}': {exc}")
            continue
        strings.update(app_strings)
    return strings

# Preferred, then fallback, TTS engine per language. openjtalk and
# piper_plus are both Japanese-capable engines (see tts_engines/); piper is
# the English engine and also the last-resort fallback if neither is
# installed. (VoiceVox was dropped as the JA fallback — it's a full HTTP
# synthesis server, too heavy to run alongside everything else on the
# target Pi Zero 2 W; piper_plus is an in-process ONNX model load instead.)
_ENGINE_FOR_LANGUAGE = {"ja": "piper_plus", "en": "piper"}
_FALLBACK_ENGINE_FOR_LANGUAGE = {"ja": "openjtalk", "en": "piper"}


class LanguagePackage(Package):
    package_id = "language"
    display_name = "Language"
    priority = 6
    capability_tags = {"i18n", "speech-language"}
    package_requires = {"storage", "tts"}

    def initialize(self) -> None:
        self._strings = _load_strings(self.resources.paths.get("apps_dir"))
        # Keep the active TTS engine consistent with whatever language was
        # persisted from a previous session, not just after a live toggle.
        self._sync_tts_engine(self.get_language())

    def _sync_tts_engine(self, language: str) -> None:
        tts_api = self.require("tts").get_public_api()
        available = set(tts_api["get_available_engines"]())
        candidates = (_ENGINE_FOR_LANGUAGE.get(language), _FALLBACK_ENGINE_FOR_LANGUAGE.get(language), "piper")
        for engine_id in candidates:
            if engine_id and engine_id in available:
                tts_api["set_engine"](engine_id)
                return
        print(f"[language] No suitable TTS engine available for language '{language}'")

    def get_language(self) -> str:
        return self.resources.shared_config.get("language", "en")

    def set_language(self, language: str) -> bool:
        if language not in ("en", "ja"):
            print(f"[language] Invalid language: {language}")
            return False
        self.resources.shared_config.set("language", language)
        self._sync_tts_engine(language)
        return True

    def toggle_language(self) -> str:
        new_language = "en" if self.get_language() == "ja" else "ja"
        self.set_language(new_language)
        return new_language

    def is_japanese(self) -> bool:
        return self.get_language() == "ja"

    def t(self, key: str, default: Optional[str] = None) -> str:
        entry = self._strings.get(key)
        if not entry:
            return default if default is not None else key
        return entry.get(self.get_language(), entry.get("en", default or key))

    def romaji_preview(self, buffer: str) -> str:
        """Live "as you type" conversion for display: every mora that's
        unambiguously resolved, plus any trailing not-yet-resolved romaji
        shown as-is (e.g. a lone consonant waiting for its vowel). No-op
        outside Japanese mode."""
        if not self.is_japanese() or not buffer:
            return buffer
        return convert_romaji_full(buffer)

    def to_speech_text(self, text: str) -> str:
        """Final conversion before text is spoken: same converter as
        romaji_preview, but any unresolved trailing romaji is still passed
        through as-is rather than silently dropped (so a not-fully-typed
        mora is still audible/visible instead of vanishing)."""
        if not self.is_japanese() or not text:
            return text
        return convert_romaji_full(text)

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "get_language": self.get_language,
            "set_language": self.set_language,
            "toggle_language": self.toggle_language,
            "is_japanese": self.is_japanese,
            "t": self.t,
            "romaji_preview": self.romaji_preview,
            "to_speech_text": self.to_speech_text,
            "available_languages": lambda: ["en", "ja"],
        }


AVAILABLE_PACKAGES = [LanguagePackage]
