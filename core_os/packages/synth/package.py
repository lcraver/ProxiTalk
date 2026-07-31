"""synth package — Synth/Sample/EffectsChain/effect classes exposed
directly (plain data/computation, no injection needed, same reasoning as
geometry's classes and sprite.Sprite). note_on/note_off/play_note/
play_sample/set_effects/stop_all are bound methods of a single shared
SynthEngine, a real-time mixer (see player.py's docstring for why it's
built that way rather than a simple per-note queue)."""

from __future__ import annotations

from typing import Any, Dict

from core_os.packages.base import Package, PackageResources
from core_os.packages.synth.effects import (
    Bitcrusher,
    Delay,
    EffectsChain,
    OnePoleFilter,
    Overdrive,
    RingModulator,
)
from core_os.packages.synth.player import SynthEngine
from core_os.packages.synth.sample import Sample
from core_os.packages.synth.synth import Synth


class SynthPackage(Package):
    package_id = "synth"
    display_name = "Synth"
    priority = 20
    capability_tags = {"audio", "synthesis"}
    core_requires = {"audio_output"}

    def initialize(self) -> None:
        self._engine = SynthEngine(self.resources.core.audio_output)

    def shutdown(self) -> None:
        self._engine.close()

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "synth": Synth,
            "sample": Sample,
            "note_on": self._engine.note_on,
            "note_off": self._engine.note_off,
            "get_visual_snapshot": self._engine.get_visual_snapshot,
            "play_note": self._engine.play_note,
            "play_sample": self._engine.play_sample,
            "set_effects": self._engine.set_effects,
            "stop_all": self._engine.stop_all,
            "effects_chain": EffectsChain,
            "bitcrusher": Bitcrusher,
            "one_pole_filter": OnePoleFilter,
            "delay": Delay,
            "overdrive": Overdrive,
            "ring_modulator": RingModulator,
        }


AVAILABLE_PACKAGES = [SynthPackage]
