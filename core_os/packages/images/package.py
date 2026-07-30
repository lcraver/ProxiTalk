"""images package — load/resize/dither images for the 1-bit display, plus
one-call draw_file()/draw_url() convenience, generalizing the same "helper
that does the common case in one call" pattern as ui.fill()/ui.content()
(see core_os/packages/ui/package.py).

Wraps core_os's own image_utils.AppImageUtils (a core_os-owned copy of the
same shape V1 apps like gallery/discourse_chat/pt_browser use via
utils/image_utils.py for downloading/dithering images), rather than
reimplementing image prep here. Those V1 apps chain three calls by hand
every time they draw a picture:

    image = AppImageUtils.load_image_from_file(path)
    processed = AppImageUtils.prepare_image_for_display(image, max_width=.., max_height=..)
    context["drawing"]["draw_image"](processed["image"], x, y)

draw_file()/draw_url() collapse that into one call for the common case
(load, resize/dither, blit); load_file()/load_url()/load_animation_*() stay
available for apps that need to hold onto the prepared image/frames
themselves (e.g. to animate a GIF frame-by-frame, or draw on the overlay
layer instead)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PIL import Image

from core_os.packages.base import Package, PackageResources
from core_os.packages.images.image_utils import AppImageUtils


class GifAnimation:
    """Cycles pre-decoded animated-image frames (see
    ImagesPackage.load_animation_file/load_animation_url) -- ported from
    proxitalk.py's play_startup_sequence(), which played a GIF by looping
    time.sleep(frame_duration) in a background thread pushing draw commands
    onto a queue. core_os has no such queue/thread: drawing is only safe on
    the single cooperative scheduler thread (see core/scheduler.py and
    animation/package.py's identical docstring), so this instead advances
    by having .update(dt) called once per frame from an app's own update()
    -- the same explicitly-ticked shape as animation.SlideIn/ScaleIn,
    just for a sequence of frames instead of a tween."""

    def __init__(self, gfx, frames: List[Image.Image], durations: List[int], x: int, y: int, loop: bool = True) -> None:
        self._gfx = gfx
        self._frames = frames
        self._durations = durations  # milliseconds, one per frame
        self.x = x
        self.y = y
        self.loop = loop
        self._index = 0
        self._elapsed_ms = 0.0
        self._done = not frames
        self._last_rect = None
        if frames:
            self._draw_frame()

    @property
    def done(self) -> bool:
        return self._done

    @property
    def frame(self) -> Optional[Image.Image]:
        return self._frames[self._index] if self._frames else None

    def _frame_duration(self) -> int:
        return self._durations[self._index] if self._durations else 100

    def _draw_frame(self) -> None:
        frame = self._frames[self._index]
        if self._last_rect is not None:
            self._gfx.clear_area(*self._last_rect)
        self._gfx.draw_image(frame, self.x, self.y)
        self._last_rect = (self.x, self.y, frame.width, frame.height)

    def update(self, dt: float) -> None:
        if self._done:
            return
        self._elapsed_ms += dt * 1000.0
        advanced = False
        while self._elapsed_ms >= self._frame_duration():
            self._elapsed_ms -= self._frame_duration()
            advanced = True
            if self._index + 1 < len(self._frames):
                self._index += 1
            elif self.loop:
                self._index = 0
            else:
                self._done = True
                break
        if advanced:
            self._draw_frame()


class ImagesPackage(Package):
    package_id = "images"
    display_name = "Images"
    priority = 25
    capability_tags = {"images"}
    package_requires = {"display_gfx"}

    def initialize(self) -> None:
        self._gfx = self.require("display_gfx")

    # --- loading (no drawing) ---------------------------------------------

    def load_file(
        self,
        path: str,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        allow_upscale: bool = False,
    ) -> Dict[str, Any]:
        return AppImageUtils.process_image_from_file(
            path, max_width=max_width, max_height=max_height, allow_upscale=allow_upscale
        )

    def load_url(
        self,
        url: str,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        allow_upscale: bool = False,
    ) -> Dict[str, Any]:
        return AppImageUtils.process_image_from_url(
            url, max_width=max_width, max_height=max_height, allow_upscale=allow_upscale
        )

    def load_animation_file(
        self,
        path: str,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        allow_upscale: bool = False,
        min_frame_duration_ms: int = 100,
    ) -> Dict[str, Any]:
        gif_image = AppImageUtils.load_image_from_file(path)
        return AppImageUtils.prepare_animation_frames(
            gif_image,
            max_width=max_width,
            max_height=max_height,
            allow_upscale=allow_upscale,
            min_frame_duration_ms=min_frame_duration_ms,
        )

    def load_animation_url(
        self,
        url: str,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        allow_upscale: bool = False,
        min_frame_duration_ms: int = 100,
    ) -> Dict[str, Any]:
        gif_image = AppImageUtils.download_image(url)
        return AppImageUtils.prepare_animation_frames(
            gif_image,
            max_width=max_width,
            max_height=max_height,
            allow_upscale=allow_upscale,
            min_frame_duration_ms=min_frame_duration_ms,
        )

    # --- load + draw in one call ------------------------------------------

    def draw_file(
        self,
        path: str,
        x: int,
        y: int,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        allow_upscale: bool = False,
        overlay: bool = False,
    ) -> Image.Image:
        prepared = self.load_file(path, max_width=max_width, max_height=max_height, allow_upscale=allow_upscale)
        self._draw(prepared["image"], x, y, overlay)
        return prepared["image"]

    def draw_url(
        self,
        url: str,
        x: int,
        y: int,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        allow_upscale: bool = False,
        overlay: bool = False,
    ) -> Image.Image:
        prepared = self.load_url(url, max_width=max_width, max_height=max_height, allow_upscale=allow_upscale)
        self._draw(prepared["image"], x, y, overlay)
        return prepared["image"]

    def _draw(self, image: Image.Image, x: int, y: int, overlay: bool) -> None:
        if overlay:
            self._gfx.draw_overlay_image(image, x, y)
        else:
            self._gfx.draw_image(image, x, y)

    # --- animated GIFs ------------------------------------------------------

    def make_animation(self, frames_data: Dict[str, Any], x: int, y: int, loop: bool = True) -> GifAnimation:
        """Wrap already-loaded frames (see load_animation_file/url) in a
        ticked GifAnimation. Split from play_animation_file/url below so an
        app that already called load_animation_file/url for other reasons
        (e.g. to measure width/height first) doesn't have to decode twice."""
        return GifAnimation(self._gfx, frames_data["frames"], frames_data["durations"], x, y, loop=loop)

    def play_animation_file(
        self,
        path: str,
        x: int,
        y: int,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        allow_upscale: bool = False,
        min_frame_duration_ms: int = 100,
        loop: bool = True,
    ) -> GifAnimation:
        frames_data = self.load_animation_file(
            path, max_width=max_width, max_height=max_height,
            allow_upscale=allow_upscale, min_frame_duration_ms=min_frame_duration_ms,
        )
        return self.make_animation(frames_data, x, y, loop=loop)

    def play_animation_url(
        self,
        url: str,
        x: int,
        y: int,
        max_width: Optional[int] = None,
        max_height: Optional[int] = None,
        allow_upscale: bool = False,
        min_frame_duration_ms: int = 100,
        loop: bool = True,
    ) -> GifAnimation:
        frames_data = self.load_animation_url(
            url, max_width=max_width, max_height=max_height,
            allow_upscale=allow_upscale, min_frame_duration_ms=min_frame_duration_ms,
        )
        return self.make_animation(frames_data, x, y, loop=loop)

    def get_public_api(self) -> Dict[str, Any]:
        return {
            "load_file": self.load_file,
            "load_url": self.load_url,
            "load_animation_file": self.load_animation_file,
            "load_animation_url": self.load_animation_url,
            "draw_file": self.draw_file,
            "draw_url": self.draw_url,
            "make_animation": self.make_animation,
            "play_animation_file": self.play_animation_file,
            "play_animation_url": self.play_animation_url,
        }


AVAILABLE_PACKAGES = [ImagesPackage]
