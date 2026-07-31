"""input package — keymap/shift-mapping helpers + a make_text_input()
factory, using core_os's own keymap.py and text_input.py."""

from __future__ import annotations

from typing import Any, Dict, Optional

from core_os.packages.base import Package, PackageResources
from core_os.packages.input.handler_stack import InputHandlerStack
from core_os.packages.input.keymap import (
    fn_key_map,
    fn_shift_key_map,
    key_map,
    shift_key_map,
)
from core_os.packages.input.text_input import TextInput

_LETTER_KEYS = {f'KEY_{c}' for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'}


class InputPackage(Package):
    package_id = "input"
    display_name = "Input"
    priority = 15
    capability_tags = {"keymap", "text-input"}
    core_requires = {"input"}

    def initialize(self) -> None:
        pass

    def apply_modifier_mapping(self, keycode: str, shift_pressed: bool, fn_pressed: bool) -> str:
        """FN takes priority over SHIFT (mirrors apply_shift_mapping, but FN
        adds a third layer), and only ever touches the letter keys -- FN
        held over ENTER/BACKSPACE/arrows/modifiers etc. must still pass
        those through untouched, so non-letter keycodes skip straight to
        the plain shift_key_map behavior regardless of fn_pressed.

        On a letter key, FN+SHIFT only defines the QWERTYUIOP -> digit row
        (fn_shift_key_map); every other letter in that combo is a dead key
        by design, so it's excluded here rather than falling back to
        fn_key_map or shift_key_map alone."""
        if keycode not in _LETTER_KEYS:
            if shift_pressed and keycode in shift_key_map:
                return shift_key_map[keycode]
            return keycode
        if fn_pressed and shift_pressed:
            return fn_shift_key_map.get(keycode, 'KEY_FN_VOID')
        if fn_pressed:
            return fn_key_map[keycode]
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
            "fn_key_map": fn_key_map,
            "fn_shift_key_map": fn_shift_key_map,
            "apply_modifier_mapping": self.apply_modifier_mapping,
            "make_text_input": self.make_text_input,
            "handler_stack": InputHandlerStack,
        }


AVAILABLE_PACKAGES = [InputPackage]
