import io
from typing import Dict, List, Optional, Tuple

import requests
from PIL import Image


class AppImageUtils:
    """Shared helpers for downloading and preparing images for the 128x64 display."""

    DEFAULT_TIMEOUT = 8
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    @classmethod
    def download_image(
        cls,
        url: str,
        *,
        timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Image.Image:
        """Download an image and return a PIL object without altering the format."""
        merged_headers = dict(cls.DEFAULT_HEADERS)
        if headers:
            merged_headers.update(headers)

        response = requests.get(url, timeout=timeout or cls.DEFAULT_TIMEOUT, headers=merged_headers)
        response.raise_for_status()

        image_bytes = io.BytesIO(response.content)
        image = Image.open(image_bytes)
        return image

    @classmethod
    def load_image_from_file(cls, file_path: str) -> Image.Image:
        """Load an image from the filesystem into memory."""
        with open(file_path, "rb") as handle:
            image_bytes = io.BytesIO(handle.read())
        return Image.open(image_bytes)

    @classmethod
    def process_image_from_file(
        cls,
        file_path: str,
        *,
        max_width: int,
        max_height: int,
        allow_upscale: bool = False,
        dither: Image.Dither = Image.Dither.FLOYDSTEINBERG,
    ) -> Dict[str, object]:
        """Load a local image file and convert it to 1-bit for the display."""
        image = cls.load_image_from_file(file_path)
        return cls.prepare_image_for_display(
            image,
            max_width=max_width,
            max_height=max_height,
            allow_upscale=allow_upscale,
            dither=dither,
        )

    @classmethod
    def process_image_from_url(
        cls,
        url: str,
        *,
        max_width: int,
        max_height: int,
        allow_upscale: bool = False,
        dither: Image.Dither = Image.Dither.FLOYDSTEINBERG,
    ) -> Dict[str, object]:
        """Download an image and convert it to a 1-bit dithered representation."""
        image = cls.download_image(url)
        return cls.prepare_image_for_display(
            image,
            max_width=max_width,
            max_height=max_height,
            allow_upscale=allow_upscale,
            dither=dither,
        )

    @classmethod
    def prepare_image_for_display(
        cls,
        image: Image.Image,
        *,
        max_width: int,
        max_height: int,
        allow_upscale: bool = False,
        dither: Image.Dither = Image.Dither.FLOYDSTEINBERG,
    ) -> Dict[str, object]:
        """Scale and dither an image for the device display."""
        working_image = cls._ensure_working_mode(image)
        new_width, new_height = cls._target_size(working_image.size, max_width, max_height, allow_upscale)

        if (new_width, new_height) != working_image.size:
            working_image = working_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        else:
            working_image = working_image.copy()

        mono_image = cls._to_monochrome(working_image, dither)
        return {"image": mono_image, "width": new_width, "height": new_height}

    @classmethod
    def prepare_animation_frames(
        cls,
        gif_image: Image.Image,
        *,
        max_width: int,
        max_height: int,
        allow_upscale: bool = False,
        dither: Image.Dither = Image.Dither.FLOYDSTEINBERG,
        min_frame_duration_ms: int = 50,
    ) -> Dict[str, List]:
        """Convert an animated image into display-ready frames and durations."""
        target_width, target_height = cls._target_size(gif_image.size, max_width, max_height, allow_upscale)
        total_frames = getattr(gif_image, "n_frames", 1)
        frames: List[Image.Image] = []
        durations: List[int] = []

        for frame_index in range(total_frames):
            gif_image.seek(frame_index)
            durations.append(max(gif_image.info.get("duration", 100), min_frame_duration_ms))
            frame_rgb = cls._ensure_working_mode(gif_image)
            if frame_rgb.size != (target_width, target_height):
                frame_rgb = frame_rgb.resize((target_width, target_height), Image.Resampling.LANCZOS)
            else:
                frame_rgb = frame_rgb.copy()
            frames.append(cls._to_monochrome(frame_rgb, dither))

        return {
            "frames": frames,
            "durations": durations,
            "width": target_width,
            "height": target_height,
        }

    @staticmethod
    def _ensure_working_mode(image: Image.Image) -> Image.Image:
        """Ensure the image is in a mode that resizes cleanly before dithering."""
        if image.mode in ("RGB", "L"):
            return image
        return image.convert("RGB")

    @staticmethod
    def _to_monochrome(image: Image.Image, dither: Image.Dither) -> Image.Image:
        gray = image.convert("L")
        return gray.convert("1", dither=dither)

    @staticmethod
    def _target_size(
        size: Tuple[int, int],
        max_width: int,
        max_height: int,
        allow_upscale: bool,
    ) -> Tuple[int, int]:
        width, height = size
        if width <= 0 or height <= 0:
            return 1, 1

        target_w = max_width or width
        target_h = max_height or height
        scale_x = target_w / width
        scale_y = target_h / height
        scale = min(scale_x, scale_y)
        if not allow_upscale:
            scale = min(scale, 1.0)

        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        return new_width, new_height