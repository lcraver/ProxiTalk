"""midi package — parse/schedule are exposed directly (pure functions, no
injection needed, same reasoning as geometry's classes). player is a
factory since MidiPlayer needs a TimerManager + the synth package's API
composed in (mirrors animation's make_doslide / sprite's
make_sprite_list)."""

from __future__ import annotations

from typing import Any, Dict

from core_os.packages.base import Package, PackageResources
from core_os.packages.midi.midi_file import parse
from core_os.packages.midi.player import MidiPlayer
from core_os.packages.midi.schedule import build_schedule


def load_file(path: str):
    with open(path, "rb") as f:
        data = f.read()
    return parse(data)


def make_player(timers, synth_api) -> MidiPlayer:
    return MidiPlayer(timers, synth_api)


class MidiPackage(Package):
    package_id = "midi"
    display_name = "MIDI"
    priority = 20
    capability_tags = {"audio", "midi"}

    def initialize(self) -> None:
        pass

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "load_file": load_file,
            "build_schedule": build_schedule,
            "player": make_player,
        }


AVAILABLE_PACKAGES = [MidiPackage]
