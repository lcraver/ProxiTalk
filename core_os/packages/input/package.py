"""input package — keymap/shift-mapping helpers + a make_text_input()
factory, using core_os's own keymap.py and text_input.py."""

from __future__ import annotations

from typing import Any, Dict, Optional

from core_os.packages.base import Package, PackageResources
from core_os.packages.input.keymap import key_map, shift_key_map
from core_os.packages.input.text_input import TextInput


class InputPackage(Package):
    package_id = "input"
    display_name = "Input"
    priority = 15
    capability_tags = {"keymap", "text-input"}
    core_requires = {"input"}

    def initialize(self) -> None:
        pass

    def apply_shift_mapping(self, keycode: str, shift_pressed: bool) -> str:
        if shift_pressed and keycode in shift_key_map:
            return shift_key_map[keycode]
        return keycode

    def make_text_input(
        self,
        autocomplete_path: Optional[str] = None,
        japanese_path: Optional[str] = None,
        max_length: int = 200,
        is_japanese_fn=None,
    ) -> TextInput:
        path = autocomplete_path or self.resources.paths.get("autocomplete_path")
        jp_path = japanese_path or self.resources.paths.get("autocomplete_japanese_path")
        if path:
            return TextInput.with_autocomplete(
                path, japanese_path=jp_path, max_length=max_length, is_japanese_fn=is_japanese_fn
            )
        return TextInput(max_length=max_length)

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "key_map": key_map,
            "shift_key_map": shift_key_map,
            "apply_shift_mapping": self.apply_shift_mapping,
            "make_text_input": self.make_text_input,
        }


AVAILABLE_PACKAGES = [InputPackage]
