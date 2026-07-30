"""animation package — small, explicitly-ticked helpers for simple UI
animations (slide-in, scale-in, or a bare value Tween for anything else).
Kept separate from `ui`/`images` since it's a cross-cutting concern — you
can tween a widget's position OR an image's size OR any arbitrary number —
rather than folded into either.

Nothing here runs on a background thread or auto-updates itself: drawing is
only safe on the single cooperative scheduler thread (see core/scheduler.py
and tween.py's docstring), so every animation object returned here is
advanced by calling .update(dt) once per frame from an app's own update().
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Union

from core_os.packages.animation.easing import EASINGS, ease_in, ease_in_out, ease_out, linear
from core_os.packages.animation.tween import Tween
from core_os.packages.base import Package, PackageResources

EasingArg = Union[str, Callable[[float], float]]


def _resolve_easing(easing: EasingArg) -> Callable[[float], float]:
    if callable(easing):
        return easing
    try:
        return EASINGS[easing]
    except KeyError:
        raise ValueError(f"Unknown easing '{easing}', expected one of {sorted(EASINGS)} or a callable") from None


class DoSlide:
    """Animates a layout-participating widget (anything with .x/.y/.set_bounds
    and .draw() — i.e. anything ui/layout_root already positions) from an
    off-screen/alternate (from_x, from_y) to wherever it's ALREADY been
    positioned. The widget's .x/.y at construction time are captured as the
    resting target, so the usual flow is: position the widget (construct it
    / run a layout pass) first, THEN wrap it in doslide().

    Moves the widget via set_bounds(x, y, width, height) each frame, not by
    poking .x/.y directly — Row/Column only position their CHILDREN during
    set_bounds(), so a composite widget (e.g. an icon+label Row nested in a
    bordered Column) whose .x is reassigned without re-running set_bounds
    would move its own border/fill but leave every child glued to its
    original spot. Leaf widgets (Label/Image/Menu) re-derive their draw
    position from .bounds either way, so this is a strict superset of the
    old behavior, not a special case for containers.

    Clears the PREVIOUS frame's (x, y, width, height) itself before each
    draw, in addition to whatever a widget's own draw() clears — a widget
    only ever clears its OWN current box, but while it's moving, ink drawn
    last frame can sit outside that box (e.g. a fixed-width container
    translating horizontally has its trailing edge recede every frame; an
    off-screen `from_x` can start outside a fixed-size panel's own resting
    bounds). Only the animation driver knows both the previous and current
    position, so it — not the widget — is what has to clear the gap.
    Requires the widget to expose .width/.height (every ui widget does)."""

    def __init__(
        self,
        gfx: Package,
        widget: Any,
        from_x: Optional[float] = None,
        from_y: Optional[float] = None,
        duration: float = 0.25,
        easing: EasingArg = "ease_out",
    ) -> None:
        self._gfx = gfx
        self._widget = widget
        self._w = getattr(widget, "width", 0)
        self._h = getattr(widget, "height", 0)
        self._last_rect: Optional[tuple] = None
        target = (float(widget.x), float(widget.y))
        start = (
            float(from_x) if from_x is not None else target[0],
            float(from_y) if from_y is not None else target[1],
        )
        self._tween = Tween(start, target, duration, _resolve_easing(easing))
        self._move_to(*start)
        self._draw()

    @property
    def done(self) -> bool:
        return self._tween.done

    def finish(self) -> None:
        """Snap straight to the resting position and draw it, as if the
        animation had simply run to completion. For when a caller needs to
        replace this slide with a fresh one (e.g. the hovered item changed
        again before this slide finished) -- abandoning it mid-flight would
        leave its widget's ink frozen wherever it last got to, with no
        further update() call ever going to clear or settle it. Calling
        this first guarantees whatever's on screen is the fully-settled
        end state before a new DoSlide starts layering its own slide-in on
        top of it."""
        if not self._tween.done:
            self.update(self._tween.duration)

    def _move_to(self, x: float, y: float) -> None:
        self._widget.set_bounds(int(round(x)), int(round(y)), self._w, self._h)

    def _current_rect(self) -> tuple:
        bounds = getattr(self._widget, "animation_bounds", None)
        if callable(bounds):
            return bounds()
        return (int(round(self._widget.x)), int(round(self._widget.y)), self._w, self._h)

    def _draw(self) -> None:
        self._gfx.begin_batch()
        if self._last_rect is not None:
            self._gfx.clear_area(*self._last_rect)
        self._widget.draw()
        self._last_rect = self._current_rect()
        self._gfx.end_batch()

    def update(self, dt: float) -> None:
        if self._tween.done:
            return
        self._tween.update(dt)
        self._move_to(*self._tween.value)
        self._draw()


class DoScale:
    """Draws an image centered at (center_x, center_y), growing from
    start_size to target_size pixels square. Re-decodes the image via
    images.draw_file at each step's size — costs a resize+dither per frame
    (see package docstring), fine for small icons; check frame timing
    before using this on anything larger."""

    def __init__(
        self,
        images: Package,
        gfx: Package,
        path: str,
        center_x: float,
        center_y: float,
        target_size: int,
        duration: float = 0.25,
        easing: EasingArg = "ease_out",
        start_size: int = 2,
    ) -> None:
        self._images = images
        self._gfx = gfx
        self._path = path
        self._center = (center_x, center_y)
        self._tween = Tween(float(start_size), float(target_size), duration, _resolve_easing(easing))
        self._last_rect: Optional[tuple] = None
        self._draw_at(self._tween.value)

    @property
    def done(self) -> bool:
        return self._tween.done

    def _draw_at(self, size: float) -> None:
        size_i = max(1, int(round(size)))
        x = int(self._center[0] - size_i / 2)
        y = int(self._center[1] - size_i / 2)
        if self._last_rect is not None:
            self._gfx.clear_area(*self._last_rect)
        self._images.draw_file(self._path, x, y, max_width=size_i, max_height=size_i)
        self._last_rect = (x, y, size_i, size_i)

    def update(self, dt: float) -> None:
        if self._tween.done:
            return
        self._tween.update(dt)
        self._draw_at(self._tween.value)


class AnimationPackage(Package):
    package_id = "animation"
    display_name = "Animation"
    priority = 27
    capability_tags = {"tween", "slide", "scale"}
    package_requires = {"images", "display_gfx"}

    def initialize(self) -> None:
        self._images = self.require("images")
        self._gfx = self.require("display_gfx")

    def make_tween(
        self,
        from_value,
        to_value,
        duration: float = 0.25,
        easing: EasingArg = "ease_out",
        on_complete: Optional[Callable[[], None]] = None,
    ) -> Tween:
        return Tween(from_value, to_value, duration, _resolve_easing(easing), on_complete=on_complete)

    def make_doslide(
        self,
        widget: Any,
        from_x: Optional[float] = None,
        from_y: Optional[float] = None,
        duration: float = 0.25,
        easing: EasingArg = "ease_out",
    ) -> DoSlide:
        return DoSlide(self._gfx, widget, from_x=from_x, from_y=from_y, duration=duration, easing=easing)

    def make_doscale(
        self,
        path: str,
        center_x: float,
        center_y: float,
        target_size: int,
        duration: float = 0.25,
        easing: EasingArg = "ease_out",
        start_size: int = 2,
    ) -> DoScale:
        return DoScale(
            self._images, self._gfx, path, center_x, center_y, target_size,
            duration=duration, easing=easing, start_size=start_size,
        )

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "tween": self.make_tween,
            "doslide": self.make_doslide,
            "doscale": self.make_doscale,
            "linear": linear,
            "ease_in": ease_in,
            "ease_out": ease_out,
            "ease_in_out": ease_in_out,
        }


AVAILABLE_PACKAGES = [AnimationPackage]
