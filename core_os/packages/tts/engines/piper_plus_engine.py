"""piper-plus (https://github.com/ayutaz/piper-plus) — an MIT-licensed Piper
fork with native Japanese voices and real SSML support (<speak>, <break>,
<prosody rate="...">), used in place of VoiceVox: VoiceVox is a full HTTP
synthesis server (a separate GUI-app-sized binary that has to be running in
the background), too heavy for the target Pi Zero 2 W, whereas piper-plus is
just an in-process ONNX model load — the same VITS-class footprint as the
Piper engine already running here.

Unlike the classic Piper engine, this isn't a subprocess+CLI wrapper: the
`piper` package (pip install piper-plus) is a real Python library, so this
loads the ONNX model directly via PiperVoice and calls synthesize() in-process
— no persistent process, no stdin/stdout IPC.

PiperVoice.synthesize() writes a complete WAV (not raw headerless PCM) with
the model's own embedded sample rate, so it's returned as-is here and goes
through audio_manager.play_audio_sync()'s existing RIFF-header auto-detection
(see TTSPackage.speak_async) — the exact same reasoning as the OpenJTalk/
VoiceVox engines: this model's actual rate doesn't have to match Piper's fixed
22050Hz raw-PCM assumption.

SSML is opt-in per call, not a separate mode: PiperVoice auto-detects text
starting with "<speak>"/"<speak ..." and parses it as SSML, plain text
otherwise (see piper/voice.py and piper/phonemize/ssml.py) — so callers just
wrap text in <speak>...</speak> when they want prosody/break control.
"""

from __future__ import annotations

import io
import os
import wave
from typing import Any, Dict, Optional

from .base import EngineResources, TTSEngine

try:
    from piper.voice import PiperVoice

    PIPER_PLUS_AVAILABLE = True
except ImportError:
    PIPER_PLUS_AVAILABLE = False
    print("[PiperPlus] Module not available, install with: pip install piper-plus")


class PiperPlusEngine(TTSEngine):
    engine_id = "piper_plus"
    display_name = "Piper Plus"
    priority = 20
    capability_tags = {"models", "ssml", "japanese"}

    def __init__(self, resources: EngineResources):
        super().__init__(resources)
        self._voice: Optional["PiperVoice"] = None
        self.model_path = resources.paths.get("piper_plus_model")

    @classmethod
    def is_available(cls, resources: EngineResources) -> bool:
        model_path = resources.paths.get("piper_plus_model")
        return PIPER_PLUS_AVAILABLE and bool(model_path) and os.path.exists(model_path)

    def initialize(self) -> None:
        if not PIPER_PLUS_AVAILABLE:
            print("[PiperPlus] Cannot initialize: piper-plus module not installed")
            return
        if not self.model_path or not os.path.exists(self.model_path):
            print(f"[PiperPlus] Model not found: {self.model_path}")
            return
        try:
            self._voice = PiperVoice.load(self.model_path)
            print(
                f"[PiperPlus] Loaded model: {os.path.basename(self.model_path)} "
                f"({self._voice.config.sample_rate}Hz, {self._voice.config.num_speakers} speaker(s))"
            )
        except Exception as exc:
            print(f"[PiperPlus] Failed to load model: {exc}")
            self._voice = None

    def synthesize(self, text: str, timeout: Optional[float] = None) -> bytes:
        if self._voice is None:
            self.initialize()
        if self._voice is None:
            return b""
        try:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav_file:
                wav_file.setframerate(self._voice.config.sample_rate)
                wav_file.setsampwidth(2)
                wav_file.setnchannels(1)
                for segment, length_scale, noise_scale in self._segments(text):
                    print(
                        f"[PiperPlus] segment={segment!r} "
                        f"length_scale={length_scale} noise_scale={noise_scale}"
                    )
                    for chunk in self._voice.synthesize_stream_raw(
                        segment, length_scale=length_scale, noise_scale=noise_scale
                    ):
                        wav_file.writeframes(chunk)
            return buf.getvalue()
        except Exception as exc:
            print(f"[PiperPlus] Synthesis failed: {exc}")
            return b""

    @staticmethod
    def _segments(text: str):
        """Split ``text`` into (sentence, length_scale, noise_scale) triples.

        Each sentence gets its own emphasis decision so mixed input like
        "Hello! Hello?" doesn't apply one utterance-wide setting picked
        from just the trailing punctuation.

        SSML (``<speak>...``) is passed through as a single unsplit segment
        — splitting it on sentence punctuation would tear apart its markup.
        """
        if text.lstrip().startswith("<speak"):
            yield text, None, None
            return
        from piper.text_splitter import split_sentences

        raw_sentences = split_sentences(text) or [text]
        # split_sentences() terminates a sentence at the *first* punctuation
        # mark it sees, so a combo like "!?"/"?!" gets cut into a real
        # sentence plus a stray punctuation-only fragment (e.g. "すごい!?"
        # -> ["すごい!", "?"]) instead of staying merged. Reattach any such
        # fragment to the sentence before it so the phonemizer sees the
        # combo intact and can pick its dedicated merged EOS token.
        _TERMINATORS = set(".!?。！？．")
        sentences = []
        for s in raw_sentences:
            if sentences and s and all(ch in _TERMINATORS for ch in s):
                sentences[-1] += s
            else:
                sentences.append(s)

        for sentence in sentences:
            length_scale, noise_scale = PiperPlusEngine._prosody_for(sentence)
            sentence = PiperPlusEngine._drop_bang_from_interrobang(sentence)
            yield sentence, length_scale, noise_scale

    @staticmethod
    def _prosody_for(sentence: str) -> tuple:
        # The bundled Japanese model's phoneme inventory has a dedicated EOS
        # token for "?"/"？" (rising, interrogative — piper's own phonemizer
        # already picks this up per sentence), but no equivalent token for
        # "!"/"！": it falls back to the same declarative "$" EOS as a
        # period, so exclamations were rendered identically to statements.
        # There's no token to add without retraining, so approximate
        # emphasis instead via faster/punchier delivery (lower length_scale,
        # higher noise_scale) whenever the sentence's terminal punctuation
        # includes "!" — regardless of whether it's alone or combined with
        # "?" (see _drop_bang_from_interrobang for the "!?"/"?!" case).
        stripped = sentence.rstrip()
        if stripped[-2:] in ("!?", "?!", "！？", "？！") or stripped.endswith(("!", "！")):
            return 0.85, 0.85
        return None, None

    @staticmethod
    def _drop_bang_from_interrobang(sentence: str) -> str:
        # For a combined "!?"/"?!" ending we want the plain interrogative
        # EOS token (rising "?" intonation, unmodified) sped up like a
        # bare "!" — not the vendored phonemizer's own distinct "?!"
        # merged-EOS phoneme, which sounds like neither. Strip the "!" out
        # of the terminal punctuation so only "?" reaches the phonemizer;
        # _prosody_for still sees the original text and applies the speed
        # boost from the "!" that was there.
        stripped = sentence.rstrip()
        trailing_ws = sentence[len(stripped):]
        if stripped[-2:] in ("!?", "?!"):
            return stripped[:-2] + "?" + trailing_ws
        if stripped[-2:] in ("！？", "？！"):
            return stripped[:-2] + "？" + trailing_ws
        return sentence

    def shutdown(self) -> None:
        self._voice = None

    def cache_identity(self) -> Dict[str, Any]:
        return {"model": os.path.basename(self.model_path) if self.model_path else "unknown"}

    def get_public_api(self) -> Dict[str, Any]:
        return {}


AVAILABLE_ENGINES = [PiperPlusEngine]
