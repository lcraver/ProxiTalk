"""Sprite/SpriteList — a retained-mode display list mirroring Playdate's
playdate.graphics.sprite: add/remove a Sprite once, then one
update_and_draw(dt) per app tick handles per-sprite update() calls, erasing
last frame's ink, and z-ordered redraw, instead of every app hand-rolling
its own "remember what I drew last frame and clear it" loop the way
animation/tween.py's DoSlide and apps/modifier_hud's _Card both already do
one-off. display_gfx has no dirty-rect/diffing system and no z-ordering
within a layer (see its docstring) -- SpriteList is what supplies both of
those on top of it, for however many sprites are added.

Redraws every visible sprite unconditionally on every update_and_draw()
call, with no per-sprite dirty-check skip -- matches the existing
convention everywhere else in this codebase (DoSlide/GifAnimation both
redraw unconditionally each active tick too); not worth the complexity at
this screen size/tick rate."""

from __future__ import annotations

from typing import Iterable, List, Optional, Set

from core_os.packages.geometry.geometry import Point, Rect


class Sprite:
    def __init__(self, image, x: float = 0.0, y: float = 0.0, z_index: int = 0, visible: bool = True) -> None:
        self.image = image
        self.x = x
        self.y = y
        self.z_index = z_index
        self.visible = visible
        # Owned by whichever SpriteList this sprite is added to -- tracks
        # the exact (x, y, w, h) last drawn so it can be cleared before the
        # next redraw, even across a move/resize/hide. Not meant to be read
        # or written by app code.
        self._last_rect: Optional[tuple] = None
        # Mirrors Playdate's sprite:setGroups()/setCollidesWithGroups() --
        # `groups` is what this sprite IS, `collides_with_groups` is what
        # it CARES about. Both empty by default means SpriteList.overlapping
        # ignores groups entirely and returns every rect-intersecting
        # sprite, so existing callers (no groups involved) see no change.
        self.groups: Set[int] = set()
        self.collides_with_groups: Set[int] = set()

    @property
    def width(self) -> int:
        return self.image.width if self.image is not None else 0

    @property
    def height(self) -> int:
        return self.image.height if self.image is not None else 0

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.width, self.height)

    def move_to(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

    def move_by(self, dx: float, dy: float) -> None:
        self.x += dx
        self.y += dy

    def set_image(self, image) -> None:
        self.image = image

    def set_z_index(self, z_index: int) -> None:
        self.z_index = z_index

    def set_visible(self, visible: bool) -> None:
        self.visible = visible

    def set_groups(self, groups: Iterable[int]) -> None:
        self.groups = set(groups)

    def set_collides_with_groups(self, groups: Iterable[int]) -> None:
        self.collides_with_groups = set(groups)

    def update(self, dt: float) -> None:
        """No-op by default -- override in a subclass for per-sprite
        behavior (movement, animation), mirroring Playdate's sprite:update()
        override pattern. Called by SpriteList.update_and_draw() once per
        tick, for every sprite in the list regardless of visibility (a
        hidden sprite can still be moving off-screen, e.g. respawning)."""


class SpriteList:
    """`layer` picks which pair of display_gfx draw/clear calls this list's
    sprites are drawn/erased with -- "base" (the default) or "overlay",
    matching the two layers general-purpose drawing can target (the third,
    cursor, is a fixed blinking-rect widget, not a drawing surface)."""

    def __init__(self, gfx, layer: str = "base") -> None:
        """`gfx` is the DisplayGfxPackage instance itself (attribute-style
        method access), not the app-facing context["display_gfx"] dict --
        this is package-internal composition, same convention
        animation.package.py's DoSlide/make_doslide already use."""
        if layer not in ("base", "overlay"):
            raise ValueError(f"SpriteList layer must be 'base' or 'overlay', got {layer!r}")
        self._gfx = gfx
        self._draw_image = gfx.draw_image if layer == "base" else gfx.draw_overlay_image
        self._clear_area = gfx.clear_area if layer == "base" else gfx.clear_overlay_area
        self._sprites: List[Sprite] = []

    def add(self, sprite: Sprite) -> None:
        if sprite not in self._sprites:
            self._sprites.append(sprite)

    def remove(self, sprite: Sprite) -> None:
        if sprite in self._sprites:
            if sprite._last_rect is not None:
                self._clear_area(*sprite._last_rect)
                sprite._last_rect = None
            self._sprites.remove(sprite)

    def clear(self) -> None:
        for sprite in list(self._sprites):
            self.remove(sprite)

    def update_and_draw(self, dt: float) -> None:
        # Collider debug overlay (emulator F2 dev HUD) -- reset to THIS
        # tick's set rather than accumulating, since a sprite's rect from
        # 3 ticks ago is stale, not something to keep drawing.
        self._gfx.clear_collider_regions()

        for sprite in self._sprites:
            sprite.update(dt)

        # Clear every sprite's PREVIOUS rect first (even hidden/no-longer-
        # visible ones), before drawing anything new -- a sprite that moved
        # or was hidden this frame must not leave a stale copy of itself
        # behind, and clearing has to happen before ANY redraw or a
        # z-ordered draw could paint into a spot about to be cleared by a
        # later sprite's own clear step.
        for sprite in self._sprites:
            if sprite._last_rect is not None:
                self._clear_area(*sprite._last_rect)
                sprite._last_rect = None

        # Ascending z_index so a higher z-index sprite's ink is the last
        # thing painted into any pixels it shares with a lower one.
        for sprite in sorted((s for s in self._sprites if s.visible and s.image is not None), key=lambda s: s.z_index):
            x, y = int(round(sprite.x)), int(round(sprite.y))
            self._draw_image(sprite.image, x, y)
            sprite._last_rect = (x, y, sprite.width, sprite.height)
            # Only sprites actually opted into collision (groups set, via
            # set_groups()) count as a "collider" -- a purely decorative
            # sprite with no groups was never going to show up in
            # overlapping() anyway, so it'd just be visual noise on F2.
            if sprite.groups:
                self._gfx.report_collider(x, y, sprite.width, sprite.height)

    def sprites_at(self, x: float, y: float) -> List[Sprite]:
        point = Point(x, y)
        return [s for s in self._sprites if s.visible and s.rect.contains_point(point)]

    def overlapping(self, sprite: Sprite) -> List[Sprite]:
        others = [s for s in self._sprites if s is not sprite and s.visible and s.rect.intersects(sprite.rect)]
        # Empty collides_with_groups (the default) means "don't filter by
        # group" -- matches Playdate only in spirit (its default is no
        # collisions at all until groups are set); this engine has no
        # physics step to gate, so unset stays permissive for existing
        # callers that never touch groups.
        if not sprite.collides_with_groups:
            return others
        return [s for s in others if s.groups & sprite.collides_with_groups]
