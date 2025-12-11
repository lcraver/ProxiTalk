"""Display helpers for ProxiTalk's emulator and hardware targets."""

from __future__ import annotations

import os
import threading
import time
from typing import List, Optional

import pygame
from PIL import Image

try:
    import ctypes
except ImportError:
    ctypes = None

EMULATOR_ICON_FILENAMES = (
    "emulator_icon.png",
)


class EmulatedDisplay:
    """Pygame-backed OLED emulator used on Windows for development."""

    def __init__(
        self,
        width: int,
        height: int,
        icon_dir: str,
        scale: int = 4,
        window_title: str = "ProxiTalk Emulated Display",
    ) -> None:
        self.width = width
        self.height = height
        self.scale = scale
        self._icon_dir = icon_dir
        self._window_title = window_title
        self._image = Image.new("1", (width, height))
        self._inverted = False

        self._update_lock = threading.Lock()
        self._pending_image: Optional[Image.Image] = None
        self._stop_event = threading.Event()

        # Debug overlay for dirty-region instrumentation
        self._debug_regions: List[dict] = []
        self._debug_overlay_duration = 1 / 20 * 5  # Show overlay for 5 frames at 20 FPS
        self._show_debug_overlay = True
        self._icon_surface = None

        self._window_focused = True
        self._focus_check_timer = 0.0

        self._thread = threading.Thread(target=self._run_pygame_loop, daemon=True)
        self._thread.start()

    def is_window_focused(self) -> bool:
        """Check if the pygame window currently has focus (Windows only)."""
        if not ctypes:
            return self._window_focused

        try:
            foreground_window = ctypes.windll.user32.GetForegroundWindow()
            title_buffer = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(foreground_window, title_buffer, 256)
            active_title = title_buffer.value
            return active_title == self._window_title
        except Exception as exc:  # pragma: no cover - focus changes are best-effort
            print(f"[Focus] Error checking window focus: {exc}")
            return self._window_focused

    def fill(self, color: int) -> None:
        with self._update_lock:
            self._image.paste(255 if color else 0, [0, 0, self.width, self.height])
            self._pending_image = self._image.copy()

    def contrast(self, level: int) -> None:  # noqa: D401 - parity with hardware API
        # Contrast is not simulated in the emulator.
        pass

    def invert(self, flag: bool) -> None:
        with self._update_lock:
            self._inverted = flag
            self._image = Image.eval(self._image, lambda px: 255 - px)
            self._pending_image = self._image.copy()

    def image(self, img: Image.Image) -> None:
        with self._update_lock:
            self._image = img.copy()
            if self._inverted:
                self._image = Image.eval(self._image, lambda px: 255 - px)
            self._pending_image = self._image.copy()

    def show(self) -> None:
        with self._update_lock:
            self._pending_image = self._image.copy()

    def add_debug_region(self, x: int, y: int, width: int, height: int) -> None:
        """Track dirty regions to visualize display updates during debugging."""
        if not self._show_debug_overlay:
            return

        with self._update_lock:
            self._debug_regions.append(
                {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "timestamp": time.time(),
                }
            )

    def _load_window_icon(self):
        """Load a custom emulator icon if one exists."""
        if self._icon_surface is not None:
            return self._icon_surface

        for filename in EMULATOR_ICON_FILENAMES:
            icon_path = os.path.join(self._icon_dir, filename)
            if not os.path.isfile(icon_path):
                continue
            try:
                surface = pygame.image.load(icon_path)
                if surface.get_width() != 32 or surface.get_height() != 32:
                    surface = pygame.transform.smoothscale(surface, (32, 32))
                self._icon_surface = surface
                print(f"[Display] Emulator icon loaded: {icon_path}")
                break
            except Exception as exc:
                print(f"[Display] Failed to load emulator icon '{icon_path}': {exc}")

        return self._icon_surface

    def _run_pygame_loop(self) -> None:
        try:
            pygame.mixer.pre_init(frequency=22050, size=-16, channels=1)
            pygame.init()
            self.screen = pygame.display.set_mode((self.width * self.scale, self.height * self.scale))
            pygame.display.set_caption(self._window_title)
            icon_surface = self._load_window_icon()
            if icon_surface:
                try:
                    if icon_surface.get_alpha() is not None:
                        icon_surface = icon_surface.convert_alpha()
                    else:
                        icon_surface = icon_surface.convert()
                    self._icon_surface = icon_surface
                    pygame.display.set_icon(icon_surface)
                except Exception as exc:
                    print(f"[Display] Failed to apply emulator icon: {exc}")
            clock = pygame.time.Clock()
            last_surface = None

            print("[Display] Pygame display initialized successfully")

            mixer_info = pygame.mixer.get_init()
            if mixer_info:
                print(f"[Display] Pygame mixer: {mixer_info[0]}Hz, {mixer_info[1]}-bit, {mixer_info[2]} channels")

        except Exception as exc:
            print(f"[Error] Failed to initialize pygame display: {exc}")
            self._stop_event.set()
            return

        try:
            while not self._stop_event.is_set():
                try:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            print("[Display] Received QUIT event")
                            self._stop_event.set()
                        elif event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
                            self._show_debug_overlay = not self._show_debug_overlay
                            print(f"[Debug] Region overlay: {'ON' if self._show_debug_overlay else 'OFF'}")
                except Exception as exc:
                    print(f"[Error] Exception in pygame event handling: {exc}")
                    continue

                current_time = time.time()

                if current_time - self._focus_check_timer > 0.5 and ctypes:
                    old_focus_state = self._window_focused
                    try:
                        foreground_window = ctypes.windll.user32.GetForegroundWindow()
                        title_buffer = ctypes.create_unicode_buffer(256)
                        ctypes.windll.user32.GetWindowTextW(foreground_window, title_buffer, 256)
                        active_title = title_buffer.value
                        self._window_focused = active_title == self._window_title
                        if old_focus_state != self._window_focused:
                            print(f"[Focus] Window focus changed: {self._window_focused}")
                    except Exception as exc:
                        print(f"[Focus] Error checking window focus: {exc}")
                    self._focus_check_timer = current_time

                needs_redraw = False

                with self._update_lock:
                    if self._pending_image:
                        img = self._pending_image
                        img_rgb = img.convert("RGB")
                        data = img_rgb.tobytes()
                        last_surface = pygame.image.fromstring(data, img.size, "RGB")
                        last_surface = pygame.transform.scale(
                            last_surface, (self.width * self.scale, self.height * self.scale)
                        )
                        needs_redraw = True
                        self._pending_image = None

                    if self._show_debug_overlay:
                        old_region_count = len(self._debug_regions)
                        self._debug_regions = [
                            region
                            for region in self._debug_regions
                            if current_time - region["timestamp"] < self._debug_overlay_duration
                        ]
                        if old_region_count != len(self._debug_regions) or self._debug_regions:
                            needs_redraw = True

                if needs_redraw and last_surface is not None:
                    self.screen.blit(last_surface, (0, 0))
                    if self._show_debug_overlay:
                        for region in self._debug_regions:
                            age = current_time - region["timestamp"]
                            alpha = max(0, min(255, int(255 * (1.0 - age / self._debug_overlay_duration))))
                            if alpha <= 0:
                                continue
                            overlay = pygame.Surface((region["width"] * self.scale, region["height"] * self.scale))
                            overlay.set_alpha(alpha // 2)
                            overlay.fill((255, 0, 0))
                            self.screen.blit(overlay, (region["x"] * self.scale, region["y"] * self.scale))
                    pygame.display.flip()

                clock.tick(12)

        except Exception as exc:
            print(f"[Error] Critical error in pygame main loop: {exc}")
            self._stop_event.set()
        finally:
            print("[Display] Pygame loop ended")

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join()
        pygame.quit()


class LumaDisplayWrapper:
    """Thin compatibility wrapper around luma.oled devices."""

    def __init__(self, device) -> None:
        self.device = device
        self.width = device.width
        self.height = device.height

    def fill(self, color: int) -> None:
        blank_image = Image.new("1", (self.width, self.height), color)
        self.device.display(blank_image)

    def show(self) -> None:
        # luma.oled's display() already flushes content.
        pass

    def image(self, img: Image.Image) -> None:
        self.device.display(img)

    def stop(self) -> None:
        self.device.cleanup()

    def contrast(self, level: int) -> None:
        self.device.contrast(level)


def create_display(
    is_windows: bool,
    width: int,
    height: int,
    icon_dir: str,
    i2c_port: int,
    i2c_address: int,
    scale: int = 4,
):
    """Instantiate the correct display implementation for the current platform."""
    if is_windows:
        return EmulatedDisplay(width, height, icon_dir, scale=scale)

    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1309

    serial = i2c(port=i2c_port, address=i2c_address)
    luma_device = ssd1309(serial)
    return LumaDisplayWrapper(luma_device)


__all__ = ["create_display", "EmulatedDisplay", "LumaDisplayWrapper"]
