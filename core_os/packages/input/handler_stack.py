"""InputHandlerStack — push/pop a whole control scheme, mirroring
Playdate's playdate.inputHandlers. An app calls .handle_key_down/up(keycode)
from its own onkeydown/onkeyup (this doesn't hook into bootstrap.py's
dispatch itself -- core_os already routes input to exactly one focused app
at a time, so there's no competing GLOBAL stack to manage the way
Playdate's single-cartridge model needs; the per-app win here is not
needing an if/elif keycode chain (or a mode flag checked in every branch)
to swap what keys do -- push a new handler table when entering a mode,
pop it on exit, and the top of the stack simply gets first refusal."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, TypedDict


class KeyBinding(TypedDict, total=False):
    down: Callable[[], None]
    up: Callable[[], None]


class Handlers(TypedDict, total=False):
    keys: Dict[str, KeyBinding]
    on_key_down: Callable[[str], bool]  # catch-all fallback; return True if consumed
    on_key_up: Callable[[str], bool]


class _Entry:
    __slots__ = ("handlers", "mask_previous")

    def __init__(self, handlers: Handlers, mask_previous: bool) -> None:
        self.handlers = handlers
        self.mask_previous = mask_previous


class InputHandlerStack:
    def __init__(self) -> None:
        self._stack: List[_Entry] = []

    def push(self, handlers: Handlers, mask_previous: bool = False) -> None:
        """`mask_previous=True` means this level swallows every key
        regardless of whether it itself handles it -- nothing lower in the
        stack ever sees the event while this entry is on top. Without it,
        an unhandled key falls through to the next entry down, and
        eventually to nothing (the caller's own onkeydown can still act on
        it -- handle_key_down/up only report whether the STACK consumed
        it)."""
        self._stack.append(_Entry(handlers, mask_previous))

    def pop(self) -> Optional[Handlers]:
        if not self._stack:
            return None
        return self._stack.pop().handlers

    def clear(self) -> None:
        self._stack.clear()

    @property
    def depth(self) -> int:
        return len(self._stack)

    def _dispatch(self, handlers: Handlers, keycode: str, kind: str) -> bool:
        keys = handlers.get("keys")
        if keys and keycode in keys:
            fn = keys[keycode].get(kind)  # type: ignore[typeddict-item]
            if fn is not None:
                fn()
                return True
        catch_all = handlers.get(f"on_key_{kind}")  # type: ignore[literal-required]
        if catch_all is not None:
            return bool(catch_all(keycode))
        return False

    def handle_key_down(self, keycode: str) -> bool:
        for entry in reversed(self._stack):
            if self._dispatch(entry.handlers, keycode, "down"):
                return True
            if entry.mask_previous:
                return False
        return False

    def handle_key_up(self, keycode: str) -> bool:
        for entry in reversed(self._stack):
            if self._dispatch(entry.handlers, keycode, "up"):
                return True
            if entry.mask_previous:
                return False
        return False
