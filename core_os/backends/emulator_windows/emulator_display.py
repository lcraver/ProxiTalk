"""Display helpers for ProxiTalk's emulator and hardware targets."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import webbrowser
from typing import Callable, List, Optional

import pygame
from PIL import Image, ImageOps

from core_os.backends.emulator_windows.voice_monitor import VoiceMonitorWindow
from core_os.packages.input.keymap import (
    fn_key_map,
    fn_shift_key_map,
    key_map,
    shift_key_map,
)

try:
    import ctypes
    import ctypes.wintypes as wintypes
except ImportError:
    ctypes = None
    wintypes = None

if ctypes:
    # Undocumented structs behind WM_UAHDRAWMENU/WM_UAHDRAWMENUITEM -- these
    # are what actually let a top-level Win32 menu BAR (not just its popup
    # dropdowns) be custom-painted. Field layout is stable/widely used (see
    # adzm/win32-custom-menubar-aero-theme) even though it's undocumented.
    class _DRAWITEMSTRUCT(ctypes.Structure):
        _fields_ = [
            ("CtlType", wintypes.UINT),
            ("CtlID", wintypes.UINT),
            ("itemID", wintypes.UINT),
            ("itemAction", wintypes.UINT),
            ("itemState", wintypes.UINT),
            ("hwndItem", wintypes.HWND),
            ("hDC", wintypes.HDC),
            ("rcItem", wintypes.RECT),
            ("itemData", ctypes.c_void_p),
        ]

    class _UAHMENU(ctypes.Structure):
        _fields_ = [
            ("hmenu", wintypes.HMENU),
            ("hdc", wintypes.HDC),
            ("dwFlags", wintypes.DWORD),
        ]

    class _UAHMENUITEMMETRICS(ctypes.Structure):
        _fields_ = [("cx", wintypes.DWORD), ("cy", wintypes.DWORD)]

    class _UAHMENUITEM(ctypes.Structure):
        _fields_ = [("iPosition", ctypes.c_int), ("umim", _UAHMENUITEMMETRICS)]

    class _UAHDRAWMENUITEM(ctypes.Structure):
        _fields_ = [("dis", _DRAWITEMSTRUCT), ("um", _UAHMENU), ("umi", _UAHMENUITEM)]

    class _MENUBARINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcBar", wintypes.RECT),
            ("hMenu", wintypes.HMENU),
            ("hwndMenu", wintypes.HWND),
            ("fBarFocused", wintypes.BOOL),
            ("fFocused", wintypes.BOOL),
        ]

    class _MENUITEMINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("fMask", wintypes.UINT),
            ("fType", wintypes.UINT),
            ("fState", wintypes.UINT),
            ("wID", wintypes.UINT),
            ("hSubMenu", wintypes.HMENU),
            ("hbmpChecked", ctypes.c_void_p),
            ("hbmpUnchecked", ctypes.c_void_p),
            ("dwItemData", ctypes.c_void_p),
            ("dwTypeData", wintypes.LPWSTR),
            ("cch", wintypes.UINT),
            ("hbmpItem", ctypes.c_void_p),
        ]

EMULATOR_ICON_FILENAMES = (
    "emulator_icon.png",
)

README_URL = "https://github.com/lcraver/ProxiTalk#readme"
WIKI_URL = "https://github.com/lcraver/ProxiTalk/wiki"

# Playdate's LCD isn't pure black/white -- panel pixels get tinted to match
# that warm off-black/off-white look instead of rendering the raw "1" mode
# bilevel image as literal (0,0,0)/(255,255,255).
_PANEL_BLACK = "#202020"
_PANEL_WHITE = "#d6d3cb"

# Native Win32 menu bar (File/View/Help) command IDs
_WM_COMMAND = 0x0111
_WM_UAHDRAWMENU = 0x0091  # undocumented -- fires to paint the menu BAR background
_WM_UAHDRAWMENUITEM = 0x0092  # undocumented -- fires per top-level item (File/View/Help)
_WM_NCACTIVATE = 0x0086
_WM_NCPAINT = 0x0085
_GWLP_WNDPROC = -4
_SM_CYMENU = 15
_OBJID_MENU = -3
_MIIM_STRING = 0x00000040
_ODS_SELECTED = 0x0001
_ODS_HOTLIGHT = 0x0040
_DT_CENTER_VCENTER_SINGLELINE = 0x1 | 0x4 | 0x20
_TRANSPARENT = 1
_RDW_INVALIDATE = 0x0001
_RDW_UPDATENOW = 0x0100
_RDW_ALLCHILDREN = 0x0080
_RDW_FRAME = 0x0400
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOSIZE = 0x0001
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19  # pre-20H1 builds
_MF_STRING = 0x0
_MF_POPUP = 0x0010
_MF_SEPARATOR = 0x0800
_MF_CHECKED = 0x0008
_MF_UNCHECKED = 0x0000
_SW_HIDE = 0
_SW_SHOW = 5
_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x00000010
_GCLP_HICON = -14
_GCLP_HICONSM = -34
_SM_CXICON = 11
_SM_CXSMICON = 49

_ID_FILE_RELOAD = 1001
_ID_FILE_QUIT = 1002
_ID_VIEW_DIRTY_REGIONS = 2001
_ID_VIEW_DEV_HUD = 2002
_ID_VIEW_OVERDRAW = 2003
_ID_VIEW_PIXEL_GRID = 2004
_ID_VIEW_DEVICE_MAP = 2005
_ID_VIEW_TERMINAL = 2006
_ID_VIEW_VOICE_MONITOR = 2007
_ID_HELP_README = 3001
_ID_HELP_WIKI = 3002
_ID_SCALE_1X = 4001
_ID_SCALE_2X = 4002
_ID_SCALE_4X = 4003
_ID_SCALE_8X = 4004
_ID_COLOR_BLUE = 5001
_ID_COLOR_RED = 5002
_ID_COLOR_YELLOW = 5003
_ID_COLOR_GREY = 5004
_COLOR_CMD_IDS = {
    _ID_COLOR_BLUE: "#0086d6",
    _ID_COLOR_RED: "#c12e1f",
    _ID_COLOR_YELLOW: "#fec601",
    _ID_COLOR_GREY: "#5b6579",
}

# Real device measurements (mm), given directly by the hardware owner --
# everything in the device-map deck (speaker width, screen-to-speaker gap,
# key size, keyboard's top offset) is derived from these ratios rather than
# picked arbitrarily, so the deck stays proportioned like the real device.
_DEVICE_SCREEN_WIDTH_MM = 60.0
_DEVICE_SCREEN_HEIGHT_MM = 30.0
_DEVICE_SPEAKER_WIDTH_MM = 39.0
_DEVICE_SCREEN_SPEAKER_GAP_MM = 3.0
_DEVICE_KEY_SIZE_MM = 6.4
_DEVICE_KEY_TOP_GAP_MM = 2.0  # keys start 2mm below the screen's bottom edge
_DEVICE_BEZEL_MM = 3.0  # screen/speaker sit 3mm in from the chassis edge
_DEVICE_KEY_LEFT_MM = 2.0  # keys start 2mm in from the chassis left edge

# Chassis background shown behind the device control map (F5) -- user-
# configurable via View > Color in the emulator's own menu bar (radio-style,
# same as the Scale submenu), not an app setting: this is cosmetic to the
# Windows dev emulator window, nothing a real device's Settings app would
# ever have a use for. Blue matches the shade this used to be hardcoded to,
# so an unconfigured device looks the same as before.
_DEFAULT_DEVICE_COLOR = "#0086d6"


def _hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

# Device control map for the debug overlay (F5) -- mirrors the TCA8418
# 6x7 matrix layout (32 alpha keys + 8 controller buttons, reusing R4-R5).
# Each entry is (label, KEY_* keycode injected on click, pygame key used only
# to light the key up live when it's pressed on the real keyboard). Home/App/
# No/Yes have no real keycode anywhere else in the codebase yet -- these four
# strings only exist because this overlay invents them; add real handling
# wherever apps should react to them before relying on it. Fn IS real --
# KEY_FN1, matching win_keycodes.py's 'left windows'/K_LSUPER binding and
# core_os/packages/input/keymap.py's fn_key_map.
_DEVICE_MAP_ALPHA_ROWS = [
    [("Tab", "KEY_TAB", pygame.K_TAB), ("Q", "KEY_Q", pygame.K_q), ("W", "KEY_W", pygame.K_w),
     ("E", "KEY_E", pygame.K_e), ("R", "KEY_R", pygame.K_r), ("T", "KEY_T", pygame.K_t),
     ("Y", "KEY_Y", pygame.K_y), ("U", "KEY_U", pygame.K_u), ("I", "KEY_I", pygame.K_i),
     ("O", "KEY_O", pygame.K_o), ("P", "KEY_P", pygame.K_p), ("Bksp", "KEY_BACKSPACE", pygame.K_BACKSPACE)],
    [("Shft", "KEY_LEFTSHIFT", pygame.K_LSHIFT), ("A", "KEY_A", pygame.K_a), ("S", "KEY_S", pygame.K_s),
     ("D", "KEY_D", pygame.K_d), ("F", "KEY_F", pygame.K_f), ("G", "KEY_G", pygame.K_g),
     ("H", "KEY_H", pygame.K_h), ("J", "KEY_J", pygame.K_j), ("K", "KEY_K", pygame.K_k),
     ("L", "KEY_L", pygame.K_l), ("Ent", "KEY_ENTER", pygame.K_RETURN)],
    [("Fn", "KEY_FN1", pygame.K_LSUPER), ("Z", "KEY_Z", pygame.K_z), ("X", "KEY_X", pygame.K_x),
     ("C", "KEY_C", pygame.K_c), ("Space", "KEY_SPACE", pygame.K_SPACE), ("V", "KEY_V", pygame.K_v),
     ("B", "KEY_B", pygame.K_b), ("N", "KEY_N", pygame.K_n), ("M", "KEY_M", pygame.K_m)],
]

# Home sits at the END of this row (where Ent used to be, before Ent moved
# up to the Shift row) -- see _layout_alpha_rows.
_DEVICE_MAP_HOME_KEY = ("Home", "KEY_HOME", pygame.K_HOME)
_DEVICE_MAP_HOME_ROW_INDEX = 2

# Shift/Ent were widened to 1.5x (see _layout_alpha_rows' width rules) --
# this row's keys now fill the available width on their own, so the usual
# cascading-stagger indent isn't needed here anymore.
_DEVICE_MAP_NO_INDENT_ROW_INDEX = 1

# Small square buttons above/below the d-pad (drawn separately -- see
# _DPAD_KEYS below for the fused cross itself).
# Modifier tiles that latch (toggle) on mouse click instead of requiring a
# held click -- see _toggle_device_map_latch's docstring-comment at its
# __init__ site for why a single mouse button needs this.
_DEVICE_MAP_LATCH_KEYCODES = {"KEY_LEFTSHIFT", "KEY_FN1"}

# Face buttons, side by side below the d-pad -- no paired Home/App row
# anymore, Home lives on the alpha keyboard now (see _DEVICE_MAP_ALPHA_ROWS).
_DEVICE_MAP_BOTTOM_BUTTONS = [("B", "KEY_YES", pygame.K_PAGEUP), ("A", "KEY_NO", pygame.K_PAGEDOWN)]

# The d-pad's four arms, keyed by position within its 3x3 footprint.
_DPAD_KEYS = {
    "up": ("Up", "KEY_UP", pygame.K_UP),
    "down": ("Down", "KEY_DOWN", pygame.K_DOWN),
    "left": ("Left", "KEY_LEFT", pygame.K_LEFT),
    "right": ("Right", "KEY_RIGHT", pygame.K_RIGHT),
}


class EmulatedDisplay:
    """Pygame-backed OLED emulator used on Windows for development."""

    def __init__(
        self,
        width: int,
        height: int,
        icon_dir: str,
        scale: int = 4,
        window_title: str = "ProxiTalk Emulator",
        physical_size: Optional[tuple] = None,
        settings_path: Optional[str] = None,
    ) -> None:
        # width/height are the addressable content area apps draw into.
        # physical_size (if larger) is the true panel/window size — the
        # border strip between the two is never pasted or eval'd into, so
        # it stays permanently blank regardless of what callers draw.
        self.width = width
        self.height = height
        self.scale = scale
        physical_w, physical_h = physical_size if physical_size else (width, height)
        self._physical_width = max(physical_w, width)
        self._physical_height = max(physical_h, height)
        # Content rect is centered in the physical panel — border is split
        # evenly on all sides rather than dumped entirely on right/bottom.
        self._offset_x = (self._physical_width - width) // 2
        self._offset_y = (self._physical_height - height) // 2
        self._icon_dir = icon_dir
        self._window_title = window_title
        self._image = Image.new("1", (self._physical_width, self._physical_height))
        self._inverted = False

        self._update_lock = threading.Lock()
        self._pending_image: Optional[Image.Image] = None
        self._stop_event = threading.Event()

        # Debug overlay for dirty-region instrumentation
        self._debug_regions: List[dict] = []
        self._debug_overlay_duration = 1 / 20 * 5  # Show overlay for 5 frames at 20 FPS
        self._show_debug_overlay = False
        self._icon_surface = None

        # Dev HUD: screen border, mouse cursor/coords, fps, focus state
        self._show_dev_overlay = False
        self._dev_font = None
        self._drag_start: Optional[tuple] = None
        self._drag_current: Optional[tuple] = None
        # Collider rects (Sprite.groups-bearing sprites only) for the current
        # app tick -- replaced wholesale every tick via clear_collider_region,
        # not accumulated/faded like _debug_regions, since a stale collider
        # rect from a few ticks ago is just wrong, not merely old.
        self._collider_regions: List[tuple] = []

        # Overdraw heatmap: reuses _debug_regions, additive-blends recent draw calls
        self._show_overdraw = False
        self._overdraw_window = 0.2

        # Pixel grid overlay: alignment guides at scaled pixel boundaries
        self._show_pixel_grid = False
        self._pixel_grid_step = 8

        # Device control map: draws the TCA8418 key layout below the panel.
        # Key size, the screen-to-speaker gap, and the keyboard's top offset
        # are all derived from the real device's measurements (see the
        # DEVICE_*_MM constants) rather than picked arbitrarily, so the whole
        # deck stays proportioned like the actual hardware at any scale.
        self._show_device_map = False
        self._device_map_margin = 10
        self._device_map_hitboxes: List[tuple] = []  # [(pygame.Rect, keycode_str), ...], rebuilt every draw
        self._device_map_mouse_held: Optional[str] = None
        # Sticky-keys latch for Shft/Fn: a mouse has one button, so it can't
        # physically hold a modifier down while also clicking a letter the
        # way two hands can on real hardware. Clicking Shft/Fn toggles it
        # "on" (real KEY_DOWN sent immediately) instead of requiring a held
        # click; the next non-modifier click consumes and releases every
        # latched modifier on its mouse-up.
        self._device_map_latched: set = set()
        self._device_map_font_cache: dict = {}  # point size -> pygame.font.Font, since keys scale with window size
        self._key_event_callback: Optional[Callable[[str, bool], None]] = None

        # Native File/View/Help menu bar (Windows only)
        self._pending_menu_commands: List[int] = []
        self._wndproc_callback = None  # keeps the ctypes callback alive
        self._old_wndproc = None
        self._debug_overlays_menu = None
        self._scale_menu = None
        self._color_menu = None
        self._view_menu = None
        self._console_hwnd = None
        self._show_terminal = False
        self._show_voice_monitor = False
        self._voice_monitor = VoiceMonitorWindow()
        self._device_color = _DEFAULT_DEVICE_COLOR

        self._window_focused = True
        self._focus_check_timer = 0.0

        # Debug overlay toggles persist across runs (dev convenience) when a
        # settings_path is given -- see _load_debug_settings/_save_debug_settings.
        self._settings_path = settings_path
        self._load_debug_settings()

        self._thread = threading.Thread(target=self._run_pygame_loop, daemon=True)
        self._thread.start()

    def _load_debug_settings(self) -> None:
        if not self._settings_path or not os.path.isfile(self._settings_path):
            return
        try:
            with open(self._settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._show_debug_overlay = bool(data.get("dirty_regions", self._show_debug_overlay))
            self._show_dev_overlay = bool(data.get("dev_hud", self._show_dev_overlay))
            self._show_overdraw = bool(data.get("overdraw", self._show_overdraw))
            self._show_pixel_grid = bool(data.get("pixel_grid", self._show_pixel_grid))
            self._show_device_map = bool(data.get("device_map", self._show_device_map))
            saved_scale = data.get("scale")
            if saved_scale in (1, 2, 4, 8):
                self.scale = saved_scale
            saved_color = data.get("device_color")
            if saved_color in _COLOR_CMD_IDS.values():
                self._device_color = saved_color
        except Exception as exc:
            print(f"[Display] Failed to load debug overlay settings: {exc}")

    def _save_debug_settings(self) -> None:
        if not self._settings_path:
            return
        data = {
            "dirty_regions": self._show_debug_overlay,
            "dev_hud": self._show_dev_overlay,
            "overdraw": self._show_overdraw,
            "pixel_grid": self._show_pixel_grid,
            "device_map": self._show_device_map,
            "scale": self.scale,
            "device_color": self._device_color,
        }
        try:
            os.makedirs(os.path.dirname(self._settings_path), exist_ok=True)
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as exc:
            print(f"[Display] Failed to save debug overlay settings: {exc}")

    def set_key_event_callback(self, callback: Optional[Callable[[str, bool], None]]) -> None:
        """Called with (keycode, is_down) when a device-map key is clicked, so
        clicks reach the same input path real key presses do."""
        self._key_event_callback = callback

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
            box = [
                self._offset_x,
                self._offset_y,
                self._offset_x + self.width,
                self._offset_y + self.height,
            ]
            self._image.paste(255 if color else 0, box)
            self._pending_image = self._image.copy()

    def contrast(self, level: int) -> None:  # noqa: D401 - parity with hardware API
        # Contrast is not simulated in the emulator.
        pass

    def invert(self, flag: bool) -> None:
        with self._update_lock:
            self._inverted = flag
            self._invert_content_region()
            self._pending_image = self._image.copy()

    def _invert_content_region(self) -> None:
        # Only the addressable content rect flips — the border strip is
        # never touched, so it can't be inverted into visibility either.
        box = (self._offset_x, self._offset_y, self._offset_x + self.width, self._offset_y + self.height)
        region = self._image.crop(box)
        region = Image.eval(region, lambda px: 255 - px)
        self._image.paste(region, (self._offset_x, self._offset_y))

    def image(self, img: Image.Image) -> None:
        with self._update_lock:
            self._image.paste(img, (self._offset_x, self._offset_y))
            if self._inverted:
                self._invert_content_region()
            self._pending_image = self._image.copy()

    def show(self) -> None:
        with self._update_lock:
            self._pending_image = self._image.copy()

    def add_debug_region(self, x: int, y: int, width: int, height: int) -> None:
        """Track dirty regions to visualize display updates during debugging."""
        if not (self._show_debug_overlay or self._show_overdraw):
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

    def clear_collider_regions(self) -> None:
        """Called once per SpriteList.update_and_draw() tick, before that
        tick's sprites report themselves -- see add_collider_region."""
        if not self._show_dev_overlay:
            return
        with self._update_lock:
            self._collider_regions = []

    def add_collider_region(self, x: int, y: int, width: int, height: int) -> None:
        """F2 dev HUD collider overlay -- one rect per Sprite that has
        set_groups() called on it (see sprite.py's SpriteList.update_and_draw),
        i.e. one that actually participates in overlapping()."""
        if not self._show_dev_overlay:
            return
        with self._update_lock:
            self._collider_regions.append((x, y, width, height))

    def _load_window_icon(self):
        """Load a custom emulator icon if one exists."""
        if self._icon_surface is not None:
            return self._icon_surface

        for filename in EMULATOR_ICON_FILENAMES:
            icon_path = os.path.join(self._icon_dir, filename)
            
            print(f"[Display] Looking for emulator icon at: {icon_path}")
            
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

    def _setup_native_menu(self) -> None:
        """Attaches a real Win32 File/View/Help menu bar to the SDL window.
        SDL has no menu widget of its own, so this reaches past pygame with
        ctypes: build the menu, hand it to the window, then subclass the
        window procedure so WM_COMMAND (menu clicks) reach us. Everything the
        subclass captures is queued and only acted on back in the main loop
        (see _process_pending_menu_commands) -- the window proc itself must
        stay fast and not touch pygame/display state directly."""
        user32 = ctypes.windll.user32
        self._declare_user32_types(user32)
        hwnd = pygame.display.get_wm_info()["window"]

        self._enable_dark_title_bar(user32, hwnd)
        self._enable_dark_classic_menus(hwnd)
        self._apply_taskbar_icon(user32, hwnd)

        # The console window backing this process (if any) -- run_dev.bat
        # launches it hidden, so start the View > Terminal checkbox off of
        # whatever its actual visibility is rather than assuming.
        console_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        self._console_hwnd = console_hwnd if console_hwnd else None
        self._show_terminal = bool(self._console_hwnd and user32.IsWindowVisible(self._console_hwnd))

        file_menu = user32.CreatePopupMenu()
        user32.AppendMenuW(file_menu, _MF_STRING, _ID_FILE_RELOAD, "Reload")
        user32.AppendMenuW(file_menu, _MF_STRING, _ID_FILE_QUIT, "Quit")

        overlays_menu = user32.CreatePopupMenu()
        user32.AppendMenuW(overlays_menu, _MF_STRING, _ID_VIEW_DIRTY_REGIONS, "Dirty Regions\tF1")
        user32.AppendMenuW(overlays_menu, _MF_STRING, _ID_VIEW_DEV_HUD, "Dev HUD\tF2")
        user32.AppendMenuW(overlays_menu, _MF_STRING, _ID_VIEW_OVERDRAW, "Overdraw Heatmap\tF3")
        user32.AppendMenuW(overlays_menu, _MF_STRING, _ID_VIEW_PIXEL_GRID, "Pixel Grid\tF4")
        user32.AppendMenuW(overlays_menu, _MF_STRING, _ID_VIEW_DEVICE_MAP, "Device Control Map\tF5")
        self._debug_overlays_menu = overlays_menu

        scale_menu = user32.CreatePopupMenu()
        user32.AppendMenuW(scale_menu, _MF_STRING, _ID_SCALE_1X, "1x")
        user32.AppendMenuW(scale_menu, _MF_STRING, _ID_SCALE_2X, "2x")
        user32.AppendMenuW(scale_menu, _MF_STRING, _ID_SCALE_4X, "4x")
        user32.AppendMenuW(scale_menu, _MF_STRING, _ID_SCALE_8X, "8x")
        self._scale_menu = scale_menu

        color_menu = user32.CreatePopupMenu()
        user32.AppendMenuW(color_menu, _MF_STRING, _ID_COLOR_BLUE, "Blue")
        user32.AppendMenuW(color_menu, _MF_STRING, _ID_COLOR_RED, "Red")
        user32.AppendMenuW(color_menu, _MF_STRING, _ID_COLOR_YELLOW, "Yellow")
        user32.AppendMenuW(color_menu, _MF_STRING, _ID_COLOR_GREY, "Grey")
        self._color_menu = color_menu

        view_menu = user32.CreatePopupMenu()
        user32.AppendMenuW(view_menu, _MF_POPUP, overlays_menu, "Debug Overlays")
        user32.AppendMenuW(view_menu, _MF_POPUP, scale_menu, "Scale")
        user32.AppendMenuW(view_menu, _MF_POPUP, color_menu, "Color")
        user32.AppendMenuW(view_menu, _MF_SEPARATOR, 0, None)
        user32.AppendMenuW(view_menu, _MF_STRING, _ID_VIEW_TERMINAL, "Terminal")
        user32.AppendMenuW(view_menu, _MF_STRING, _ID_VIEW_VOICE_MONITOR, "Voice Monitor")
        self._view_menu = view_menu

        help_menu = user32.CreatePopupMenu()
        user32.AppendMenuW(help_menu, _MF_STRING, _ID_HELP_README, "README")
        user32.AppendMenuW(help_menu, _MF_STRING, _ID_HELP_WIKI, "Wiki")

        menu_bar = user32.CreateMenu()
        user32.AppendMenuW(menu_bar, _MF_POPUP, file_menu, "File")
        user32.AppendMenuW(menu_bar, _MF_POPUP, view_menu, "View")
        user32.AppendMenuW(menu_bar, _MF_POPUP, help_menu, "Help")
        user32.SetMenu(hwnd, menu_bar)
        self._sync_view_menu_checks()
        self._sync_scale_menu_checks()
        self._sync_color_menu_checks()

        # SetMenu shrinks the client area into whatever space is left in the
        # existing window frame instead of growing the window, so claw back
        # the menu bar's height once here. Later resizes (F5's device map)
        # go through pygame.display.set_mode(), which asks SDL to size the
        # window from the desired client rect and SDL itself accounts for
        # any attached menu -- so this one-time fixup is enough.
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        menu_height = user32.GetSystemMetrics(_SM_CYMENU)
        user32.SetWindowPos(
            hwnd, None, 0, 0,
            rect.right - rect.left,
            (rect.bottom - rect.top) + menu_height,
            _SWP_NOMOVE | _SWP_NOZORDER,
        )

        wndproc_type = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)
        self._wndproc_callback = wndproc_type(self._wndproc)
        self._old_wndproc = user32.SetWindowLongPtrW(
            hwnd, _GWLP_WNDPROC, ctypes.cast(self._wndproc_callback, ctypes.c_void_p)
        )
        self._redraw_menu_bar_frame(hwnd)
        self._draw_menu_bar_bottom_line(hwnd)
        print("[Display] Native menu bar attached (File/View/Help)")

    @staticmethod
    def _enable_dark_title_bar(user32, hwnd) -> None:
        """DWMWA_USE_IMMERSIVE_DARK_MODE -- documented, Windows 10 20H1+."""
        try:
            dwmapi = ctypes.windll.dwmapi
            dwmapi.DwmSetWindowAttribute.argtypes = [
                wintypes.HWND, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint,
            ]
            dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
            value = ctypes.c_int(1)
            result = dwmapi.DwmSetWindowAttribute(
                hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result != 0:  # older attribute number on pre-20H1 builds
                dwmapi.DwmSetWindowAttribute(
                    hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(value), ctypes.sizeof(value)
                )
            # Dark mode alone doesn't always repaint the existing title bar --
            # force a non-client repaint so it takes effect immediately.
            user32.SetWindowPos(
                hwnd, None, 0, 0, 0, 0,
                _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED,
            )
        except Exception as exc:
            print(f"[Display] Could not enable dark title bar: {exc}")

    @staticmethod
    def _enable_dark_classic_menus(hwnd) -> None:
        """Classic Win32 menus (the File/View/Help bar itself, not just its
        dropdowns) don't follow DWMWA_USE_IMMERSIVE_DARK_MODE -- they need
        uxtheme's undocumented dark-mode trio, the same private API dark-mode
        patches for Notepad++/Windows Terminal etc. rely on:
          - SetPreferredAppMode (ordinal 135): opt the process into dark mode
          - AllowDarkModeForWindow (ordinal 133): opt THIS window in specifically
            -- without this the menu *bar* (as opposed to its popups) stays light
          - FlushMenuThemes (ordinal 136): make it take effect immediately
        Best-effort: if a Windows build/uxtheme version doesn't have these
        ordinals, the menu just stays the default light color -- not fatal."""
        try:
            uxtheme = ctypes.WinDLL("uxtheme", use_last_error=True)
            set_preferred_app_mode = uxtheme[135]
            set_preferred_app_mode.restype = ctypes.c_int
            set_preferred_app_mode.argtypes = [ctypes.c_int]
            set_preferred_app_mode(2)  # 2 = ForceDark

            allow_dark_mode_for_window = uxtheme[133]
            allow_dark_mode_for_window.restype = ctypes.c_bool
            allow_dark_mode_for_window.argtypes = [wintypes.HWND, ctypes.c_bool]
            allow_dark_mode_for_window(hwnd, True)

            flush_menu_themes = uxtheme[136]
            flush_menu_themes()
        except Exception as exc:
            print(f"[Display] Could not enable dark classic menus: {exc}")

    def _apply_taskbar_icon(self, user32, hwnd) -> None:
        """Explicitly pushes the titlebar icon into the taskbar/Alt-Tab slot
        too. pygame.display.set_icon (SDL) reliably sets the small titlebar
        icon but not the big one the taskbar reads, so without this the
        taskbar falls back to python.exe's icon while the titlebar shows
        ours. Builds a multi-resolution .ico next to the source PNG (cached,
        rebuilt only if the PNG is newer) since LoadImageW can't decode PNG
        directly, then applies it via WM_SETICON and the window class icon
        slots (some Windows versions read the class icon for the taskbar)."""
        png_path = None
        for filename in EMULATOR_ICON_FILENAMES:
            candidate = os.path.join(self._icon_dir, filename)
            if os.path.isfile(candidate):
                png_path = candidate
                break
        if png_path is None:
            return

        ico_path = os.path.splitext(png_path)[0] + ".ico"
        try:
            if not os.path.isfile(ico_path) or os.path.getmtime(ico_path) < os.path.getmtime(png_path):
                Image.open(png_path).convert("RGBA").save(
                    ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)]
                )
        except Exception as exc:
            print(f"[Display] Failed to build .ico from '{png_path}': {exc}")
            return

        try:
            small_size = user32.GetSystemMetrics(_SM_CXSMICON)
            big_size = user32.GetSystemMetrics(_SM_CXICON)
            icon_small = user32.LoadImageW(None, ico_path, _IMAGE_ICON, small_size, small_size, _LR_LOADFROMFILE)
            icon_big = user32.LoadImageW(None, ico_path, _IMAGE_ICON, big_size, big_size, _LR_LOADFROMFILE)

            if icon_small:
                user32.SendMessageW(hwnd, _WM_SETICON, _ICON_SMALL, icon_small)
                user32.SetClassLongPtrW(hwnd, _GCLP_HICONSM, icon_small)
            if icon_big:
                user32.SendMessageW(hwnd, _WM_SETICON, _ICON_BIG, icon_big)
                user32.SetClassLongPtrW(hwnd, _GCLP_HICON, icon_big)
        except Exception as exc:
            print(f"[Display] Failed to apply taskbar icon: {exc}")

    @staticmethod
    def _declare_user32_types(user32) -> None:
        # ctypes defaults every arg/return to 32-bit c_int; on 64-bit Windows
        # that truncates HWND/HMENU/LRESULT pointers into garbage. Every
        # function here that passes a handle or pointer-sized value MUST have
        # its argtypes/restype declared explicitly, or CallWindowProcW's
        # forwarded messages silently corrupt (this broke SDL's own window
        # frame painting the first time around -- see git history).
        user32.CreateMenu.restype = wintypes.HMENU
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_void_p, wintypes.LPCWSTR]
        user32.AppendMenuW.restype = wintypes.BOOL
        user32.SetMenu.argtypes = [wintypes.HWND, wintypes.HMENU]
        user32.SetMenu.restype = wintypes.BOOL
        user32.CheckMenuItem.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
        user32.CheckMenuItem.restype = wintypes.DWORD
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        user32.CallWindowProcW.restype = ctypes.c_longlong
        user32.GetMenuBarInfo.argtypes = [wintypes.HWND, ctypes.c_long, ctypes.c_long, ctypes.POINTER(_MENUBARINFO)]
        user32.GetMenuBarInfo.restype = wintypes.BOOL
        user32.GetMenuItemInfoW.argtypes = [
            wintypes.HMENU, wintypes.UINT, wintypes.BOOL, ctypes.POINTER(_MENUITEMINFOW),
        ]
        user32.GetMenuItemInfoW.restype = wintypes.BOOL
        user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
        user32.FillRect.restype = ctypes.c_int
        user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.RECT), wintypes.UINT]
        user32.DrawTextW.restype = ctypes.c_int
        user32.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
        user32.RedrawWindow.restype = wintypes.BOOL
        user32.GetWindowDC.argtypes = [wintypes.HWND]
        user32.GetWindowDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = ctypes.c_int
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p]
        user32.SendMessageW.restype = ctypes.c_longlong
        user32.SetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.SetClassLongPtrW.restype = ctypes.c_void_p

        kernel32 = ctypes.windll.kernel32
        kernel32.GetConsoleWindow.restype = wintypes.HWND

        gdi32 = ctypes.windll.gdi32
        gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
        gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
        gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
        gdi32.SetBkMode.restype = ctypes.c_int
        gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.DWORD]
        gdi32.SetTextColor.restype = wintypes.DWORD

    @staticmethod
    def _colorref(rgb: tuple) -> int:
        r, g, b = rgb
        return (b << 16) | (g << 8) | r

    def _draw_dark_menu_bar_background(self, hwnd, lparam) -> bool:
        """WM_UAHDRAWMENU handler -- paints the menu bar's own background
        (behind File/View/Help) dark. Returns False on any failure so the
        caller falls back to default (light) rendering instead of crashing."""
        try:
            user32 = ctypes.windll.user32
            menu = ctypes.cast(lparam, ctypes.POINTER(_UAHMENU)).contents
            mbi = _MENUBARINFO()
            mbi.cbSize = ctypes.sizeof(_MENUBARINFO)
            if not user32.GetMenuBarInfo(hwnd, _OBJID_MENU, 0, ctypes.byref(mbi)):
                return False
            window_rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(window_rect))
            bar_rect = wintypes.RECT(
                mbi.rcBar.left - window_rect.left,
                mbi.rcBar.top - window_rect.top,
                mbi.rcBar.right - window_rect.left,
                mbi.rcBar.bottom - window_rect.top,
            )
            brush = ctypes.windll.gdi32.CreateSolidBrush(self._colorref((32, 32, 34)))
            user32.FillRect(menu.hdc, ctypes.byref(bar_rect), brush)
            ctypes.windll.gdi32.DeleteObject(brush)
            return True
        except Exception as exc:
            print(f"[Display] Dark menu bar background draw failed: {exc}")
            return False

    def _draw_dark_menu_bar_item(self, lparam) -> bool:
        """WM_UAHDRAWMENUITEM handler -- paints one top-level item's
        background + label (File, View, or Help) dark, including hover/
        selected highlight. Returns False on any failure so the caller falls
        back to default (light) rendering instead of crashing."""
        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            item = ctypes.cast(lparam, ctypes.POINTER(_UAHDRAWMENUITEM)).contents
            dis = item.dis

            selected = bool(dis.itemState & (_ODS_SELECTED | _ODS_HOTLIGHT))
            brush = gdi32.CreateSolidBrush(self._colorref((55, 55, 60) if selected else (32, 32, 34)))
            user32.FillRect(dis.hDC, ctypes.byref(dis.rcItem), brush)
            gdi32.DeleteObject(brush)

            buf = ctypes.create_unicode_buffer(256)
            mii = _MENUITEMINFOW()
            mii.cbSize = ctypes.sizeof(_MENUITEMINFOW)
            mii.fMask = _MIIM_STRING
            mii.dwTypeData = ctypes.cast(buf, wintypes.LPWSTR)
            mii.cch = 256
            if not user32.GetMenuItemInfoW(item.um.hmenu, item.umi.iPosition, True, ctypes.byref(mii)):
                return False

            gdi32.SetBkMode(dis.hDC, _TRANSPARENT)
            gdi32.SetTextColor(dis.hDC, self._colorref((230, 230, 230)))
            user32.DrawTextW(dis.hDC, buf.value, -1, ctypes.byref(dis.rcItem), _DT_CENTER_VCENTER_SINGLELINE)
            return True
        except Exception as exc:
            print(f"[Display] Dark menu bar item draw failed: {exc}")
            return False

    def _draw_menu_bar_bottom_line(self, hwnd) -> None:
        """Windows draws a 1px light separator directly below the menu bar
        as part of the non-client frame itself -- it's not part of rcBar, so
        WM_UAHDRAWMENU's background fill never reaches it and it stays light
        even with the rest of the bar painted dark. Repaint that row here,
        straight onto the window's non-client DC, after every NC repaint
        (see adzm/win32-custom-menubar-aero-theme's UAHDrawMenuNCBottomLine)."""
        try:
            user32 = ctypes.windll.user32
            mbi = _MENUBARINFO()
            mbi.cbSize = ctypes.sizeof(_MENUBARINFO)
            if not user32.GetMenuBarInfo(hwnd, _OBJID_MENU, 0, ctypes.byref(mbi)):
                return
            window_rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(window_rect))
            line_rect = wintypes.RECT(
                mbi.rcBar.left - window_rect.left,
                mbi.rcBar.bottom - window_rect.top,
                mbi.rcBar.right - window_rect.left,
                mbi.rcBar.bottom - window_rect.top + 1,
            )
            hdc = user32.GetWindowDC(hwnd)
            if not hdc:
                return
            try:
                brush = ctypes.windll.gdi32.CreateSolidBrush(self._colorref((32, 32, 34)))
                user32.FillRect(hdc, ctypes.byref(line_rect), brush)
                ctypes.windll.gdi32.DeleteObject(brush)
            finally:
                user32.ReleaseDC(hwnd, hdc)
        except Exception as exc:
            print(f"[Display] Menu bar bottom line draw failed: {exc}")

    def _redraw_menu_bar_frame(self, hwnd) -> None:
        """After activation/focus changes, Windows can repaint the frame (and
        the menu bar with it) back to its default light look -- force the
        whole non-client frame to redraw so our dark paint sticks."""
        try:
            ctypes.windll.user32.RedrawWindow(
                hwnd, None, None, _RDW_INVALIDATE | _RDW_UPDATENOW | _RDW_FRAME | _RDW_ALLCHILDREN
            )
        except Exception as exc:
            print(f"[Display] Menu bar frame redraw failed: {exc}")

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == _WM_COMMAND:
            self._pending_menu_commands.append(wparam & 0xFFFF)
            return 0
        if msg == _WM_UAHDRAWMENU:
            if self._draw_dark_menu_bar_background(hwnd, lparam):
                return 0
        elif msg == _WM_UAHDRAWMENUITEM:
            if self._draw_dark_menu_bar_item(lparam):
                return 0
        elif msg == _WM_NCACTIVATE:
            result = ctypes.windll.user32.CallWindowProcW(self._old_wndproc, hwnd, msg, wparam, lparam)
            self._redraw_menu_bar_frame(hwnd)
            self._draw_menu_bar_bottom_line(hwnd)
            return result
        elif msg == _WM_NCPAINT:
            result = ctypes.windll.user32.CallWindowProcW(self._old_wndproc, hwnd, msg, wparam, lparam)
            self._draw_menu_bar_bottom_line(hwnd)
            return result
        return ctypes.windll.user32.CallWindowProcW(self._old_wndproc, hwnd, msg, wparam, lparam)

    def _sync_view_menu_checks(self) -> None:
        """Called after every overlay toggle (hotkey or menu click) so the
        Debug Overlays submenu's checkmarks always match reality, and the new
        state is persisted (see settings_path/_load_debug_settings) so it
        survives the next run."""
        self._save_debug_settings()
        user32 = ctypes.windll.user32
        if self._view_menu is not None:
            user32.CheckMenuItem(
                self._view_menu, _ID_VIEW_TERMINAL, _MF_CHECKED if self._show_terminal else _MF_UNCHECKED
            )
            user32.CheckMenuItem(
                self._view_menu, _ID_VIEW_VOICE_MONITOR, _MF_CHECKED if self._show_voice_monitor else _MF_UNCHECKED
            )
        if self._debug_overlays_menu is None:
            return
        for cmd_id, flag in (
            (_ID_VIEW_DIRTY_REGIONS, self._show_debug_overlay),
            (_ID_VIEW_DEV_HUD, self._show_dev_overlay),
            (_ID_VIEW_OVERDRAW, self._show_overdraw),
            (_ID_VIEW_PIXEL_GRID, self._show_pixel_grid),
            (_ID_VIEW_DEVICE_MAP, self._show_device_map),
        ):
            user32.CheckMenuItem(self._debug_overlays_menu, cmd_id, _MF_CHECKED if flag else _MF_UNCHECKED)

    def _on_voice_monitor_closed(self) -> None:
        """Runs on the Voice Monitor's own Tk thread when its window is
        closed via the OS close button rather than the View menu, so the
        menu checkmark doesn't stay stuck on."""
        self._show_voice_monitor = False
        self._sync_view_menu_checks()

    def _set_console_visible(self, visible: bool) -> None:
        if not self._console_hwnd:
            return
        try:
            ctypes.windll.user32.ShowWindow(self._console_hwnd, _SW_SHOW if visible else _SW_HIDE)
        except Exception as exc:
            print(f"[Display] Failed to toggle terminal visibility: {exc}")

    def _sync_scale_menu_checks(self) -> None:
        """Radio-style: exactly one of 1x/2x/4x/8x is checked, matching self.scale."""
        self._save_debug_settings()
        if self._scale_menu is None:
            return
        user32 = ctypes.windll.user32
        for cmd_id, scale_value in (
            (_ID_SCALE_1X, 1),
            (_ID_SCALE_2X, 2),
            (_ID_SCALE_4X, 4),
            (_ID_SCALE_8X, 8),
        ):
            user32.CheckMenuItem(self._scale_menu, cmd_id, _MF_CHECKED if self.scale == scale_value else _MF_UNCHECKED)

    def _sync_color_menu_checks(self) -> None:
        """Radio-style: exactly one of Blue/Red/Yellow/Grey is checked, matching self._device_color."""
        self._save_debug_settings()
        if self._color_menu is None:
            return
        user32 = ctypes.windll.user32
        for cmd_id, color_value in _COLOR_CMD_IDS.items():
            user32.CheckMenuItem(
                self._color_menu, cmd_id, _MF_CHECKED if self._device_color == color_value else _MF_UNCHECKED
            )

    def _process_pending_menu_commands(self) -> None:
        commands, self._pending_menu_commands = self._pending_menu_commands, []
        for cmd_id in commands:
            if cmd_id == _ID_FILE_QUIT:
                print("[Display] Quit selected from File menu")
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            elif cmd_id == _ID_FILE_RELOAD:
                print("[Display] Reload selected from File menu — restarting process")
                os.execv(sys.executable, [sys.executable] + sys.argv)
            elif cmd_id == _ID_VIEW_DIRTY_REGIONS:
                self._show_debug_overlay = not self._show_debug_overlay
            elif cmd_id == _ID_VIEW_DEV_HUD:
                self._show_dev_overlay = not self._show_dev_overlay
            elif cmd_id == _ID_VIEW_OVERDRAW:
                self._show_overdraw = not self._show_overdraw
            elif cmd_id == _ID_VIEW_PIXEL_GRID:
                self._show_pixel_grid = not self._show_pixel_grid
            elif cmd_id == _ID_VIEW_DEVICE_MAP:
                self._show_device_map = not self._show_device_map
                self.screen = self._resize_for_device_map()
            elif cmd_id == _ID_VIEW_TERMINAL:
                self._show_terminal = not self._show_terminal
                self._set_console_visible(self._show_terminal)
            elif cmd_id == _ID_VIEW_VOICE_MONITOR:
                self._show_voice_monitor = not self._show_voice_monitor
                if self._show_voice_monitor:
                    self._voice_monitor.open(on_close=self._on_voice_monitor_closed)
                else:
                    self._voice_monitor.close()
            elif cmd_id == _ID_HELP_README:
                webbrowser.open(README_URL)
            elif cmd_id == _ID_HELP_WIKI:
                webbrowser.open(WIKI_URL)
            elif cmd_id in (_ID_SCALE_1X, _ID_SCALE_2X, _ID_SCALE_4X, _ID_SCALE_8X):
                self.scale = {_ID_SCALE_1X: 1, _ID_SCALE_2X: 2, _ID_SCALE_4X: 4, _ID_SCALE_8X: 8}[cmd_id]
                self.screen = self._resize_for_device_map()
                self._sync_scale_menu_checks()
                continue
            elif cmd_id in _COLOR_CMD_IDS:
                self._device_color = _COLOR_CMD_IDS[cmd_id]
                self._sync_color_menu_checks()
                continue
            else:
                continue
            self._sync_view_menu_checks()

    def _run_pygame_loop(self) -> None:
        try:
            if ctypes:
                try:
                    # Without a distinct AppUserModelID, Windows taskbars this
                    # process under python.exe's own identity -- the WM_SETICON
                    # calls in _apply_taskbar_icon still land, but the taskbar
                    # keeps grouping/caching the button against python.exe's
                    # default icon, so it shows through anyway. Must happen
                    # before the window exists for Windows to pick it up.
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ProxiTalk.Emulator")
                except Exception as exc:
                    print(f"[Display] Failed to set AppUserModelID: {exc}")
            pygame.mixer.pre_init(frequency=22050, size=-16, channels=1)
            pygame.init()
            self.screen = pygame.display.set_mode((self._physical_width * self.scale, self._physical_height * self.scale))
            pygame.display.set_caption(self._window_title)
            
            print(f"[Display] Pygame initialized with display size {self.width}x{self.height} (scale {self.scale}x) and physical size {self._physical_width}x{self._physical_height}")
            print(f"[Display] Pygame version: {pygame.version.ver}")
            print(f"[Display] Icon directory: {self._icon_dir}")
            
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
            self._dev_font = pygame.font.SysFont("consolas", 14)

            if ctypes:
                try:
                    self._setup_native_menu()
                except Exception as exc:
                    print(f"[Display] Failed to install native menu bar: {exc}")

            if self._show_device_map:
                self.screen = self._resize_for_device_map()

            print("[Display] Pygame display initialized successfully")
            print(
                "[Display] Dev keys: F1 dirty regions, F2 dev HUD (mouse/border/drag-select/colliders), "
                "F3 overdraw heatmap, F4 pixel grid, F5 device control map"
            )

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
                            self._sync_view_menu_checks()
                        elif event.type == pygame.KEYDOWN and event.key == pygame.K_F2:
                            self._show_dev_overlay = not self._show_dev_overlay
                            print(f"[Debug] Dev HUD: {'ON' if self._show_dev_overlay else 'OFF'}")
                            self._sync_view_menu_checks()
                        elif event.type == pygame.KEYDOWN and event.key == pygame.K_F3:
                            self._show_overdraw = not self._show_overdraw
                            print(f"[Debug] Overdraw heatmap: {'ON' if self._show_overdraw else 'OFF'}")
                            self._sync_view_menu_checks()
                        elif event.type == pygame.KEYDOWN and event.key == pygame.K_F4:
                            self._show_pixel_grid = not self._show_pixel_grid
                            print(f"[Debug] Pixel grid: {'ON' if self._show_pixel_grid else 'OFF'}")
                            self._sync_view_menu_checks()
                        elif event.type == pygame.KEYDOWN and event.key == pygame.K_F5:
                            self._show_device_map = not self._show_device_map
                            print(f"[Debug] Device control map: {'ON' if self._show_device_map else 'OFF'}")
                            self.screen = self._resize_for_device_map()
                            self._sync_view_menu_checks()
                        elif (
                            self._show_device_map
                            and event.type == pygame.MOUSEBUTTONDOWN
                            and event.button == 1
                        ):
                            self._handle_device_map_mouse_down(event.pos)
                        elif (
                            self._show_device_map
                            and event.type == pygame.MOUSEBUTTONUP
                            and event.button == 1
                        ):
                            self._handle_device_map_mouse_up()
                        elif (
                            self._show_dev_overlay
                            and event.type == pygame.MOUSEBUTTONDOWN
                            and event.button == 1
                        ):
                            self._drag_start = event.pos
                            self._drag_current = event.pos
                        elif self._show_dev_overlay and event.type == pygame.MOUSEMOTION and self._drag_start:
                            self._drag_current = event.pos
                        elif (
                            self._show_dev_overlay
                            and event.type == pygame.MOUSEBUTTONUP
                            and event.button == 1
                            and self._drag_start
                        ):
                            self._drag_current = event.pos
                            self._copy_selection_to_clipboard()
                            self._drag_start = None
                            self._drag_current = None
                except Exception as exc:
                    print(f"[Error] Exception in pygame event handling: {exc}")
                    continue

                if self._pending_menu_commands:
                    self._process_pending_menu_commands()

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

                needs_redraw = (
                    self._show_dev_overlay or self._show_overdraw or self._show_pixel_grid or self._show_device_map
                )

                with self._update_lock:
                    if self._pending_image:
                        img = self._pending_image
                        img_rgb = ImageOps.colorize(img.convert("L"), black=_PANEL_BLACK, white=_PANEL_WHITE)
                        data = img_rgb.tobytes()
                        last_surface = pygame.image.fromstring(data, img.size, "RGB")
                        last_surface = pygame.transform.scale(
                            last_surface, (img.size[0] * self.scale, img.size[1] * self.scale)
                        )
                        last_surface = self._round_surface_corners(last_surface, radius=2)
                        needs_redraw = True
                        self._pending_image = None

                    if self._show_debug_overlay or self._show_overdraw:
                        old_region_count = len(self._debug_regions)
                        retention = max(self._debug_overlay_duration, self._overdraw_window)
                        self._debug_regions = [
                            region
                            for region in self._debug_regions
                            if current_time - region["timestamp"] < retention
                        ]
                        if old_region_count != len(self._debug_regions) or self._debug_regions:
                            needs_redraw = True

                if needs_redraw and (
                    last_surface is not None
                    or self._show_dev_overlay
                    or self._show_overdraw
                    or self._show_pixel_grid
                    or self._show_device_map
                ):
                    if self._show_device_map:
                        # Canvas may extend past the panel to fit the key map,
                        # so clear the whole thing before blitting the panel.
                        self.screen.fill(_hex_to_rgb(self._device_color))
                    if last_surface is not None:
                        self.screen.blit(last_surface, self._screen_origin_px())
                    elif not self._show_device_map:
                        self.screen.fill((0, 0, 0))
                    if self._show_debug_overlay:
                        origin_x, origin_y = self._screen_origin_px()
                        for region in self._debug_regions:
                            age = current_time - region["timestamp"]
                            alpha = max(0, min(255, int(255 * (1.0 - age / self._debug_overlay_duration))))
                            if alpha <= 0:
                                continue
                            overlay = pygame.Surface((region["width"] * self.scale, region["height"] * self.scale))
                            overlay.set_alpha(alpha // 2)
                            overlay.fill((255, 0, 0))
                            self.screen.blit(
                                overlay,
                                (
                                    origin_x + (region["x"] + self._offset_x) * self.scale,
                                    origin_y + (region["y"] + self._offset_y) * self.scale,
                                ),
                            )
                    if self._show_overdraw:
                        self._draw_overdraw(current_time)
                    if self._show_pixel_grid:
                        self._draw_pixel_grid()
                    if self._show_dev_overlay:
                        self._draw_dev_overlay(clock)
                    if self._show_device_map:
                        self._draw_device_map()
                    pygame.display.flip()

                clock.tick(60)

        except Exception as exc:
            print(f"[Error] Critical error in pygame main loop: {exc}")
            self._stop_event.set()
        finally:
            print("[Display] Pygame loop ended")

    def _selection_rect_logical(self) -> Optional[tuple]:
        """Return (x, y, w, h) of the in-progress drag selection in logical px, or None."""
        if not self._drag_start or not self._drag_current:
            return None
        x0, y0 = self._drag_start
        x1, y1 = self._drag_current
        left, top = min(x0, x1), min(y0, y1)
        right, bottom = max(x0, x1), max(y0, y1)
        origin_x, origin_y = self._screen_origin_px()
        lx = (left - origin_x) // self.scale - self._offset_x
        ly = (top - origin_y) // self.scale - self._offset_y
        lw = (right // self.scale) - (left // self.scale)
        lh = (bottom // self.scale) - (top // self.scale)
        return lx, ly, lw, lh

    def _copy_selection_to_clipboard(self) -> None:
        rect = self._selection_rect_logical()
        if rect is None:
            return
        x, y, w, h = rect
        text = f"x={x}, y={y}, w={w}, h={h}"
        try:
            import tkinter

            root = tkinter.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            print(f"[Dev] Copied selection to clipboard: {text}")
        except Exception as exc:
            print(f"[Dev] Failed to copy selection '{text}' to clipboard: {exc}")

    def _draw_overdraw(self, current_time: float) -> None:
        """Additive-blend recent draw-call regions so overlapping paints glow hotter."""
        origin_x, origin_y = self._screen_origin_px()
        for region in self._debug_regions:
            if current_time - region["timestamp"] >= self._overdraw_window:
                continue
            rect = (
                origin_x + (region["x"] + self._offset_x) * self.scale,
                origin_y + (region["y"] + self._offset_y) * self.scale,
                region["width"] * self.scale,
                region["height"] * self.scale,
            )
            self.screen.fill((24, 0, 0), rect, special_flags=pygame.BLEND_RGB_ADD)

    def _draw_pixel_grid(self) -> None:
        """Draw alignment guides at fixed logical-pixel intervals, within the content rect."""
        step = self._pixel_grid_step
        grid_color = (0, 100, 0)
        origin_x, origin_y = self._screen_origin_px()
        top = origin_y + self._offset_y * self.scale
        bottom = origin_y + (self._offset_y + self.height) * self.scale
        left = origin_x + self._offset_x * self.scale
        right = origin_x + (self._offset_x + self.width) * self.scale
        for gx in range(0, self.width + 1, step):
            px = origin_x + (self._offset_x + gx) * self.scale
            pygame.draw.line(self.screen, grid_color, (px, top), (px, bottom), 1)
        for gy in range(0, self.height + 1, step):
            py = origin_y + (self._offset_y + gy) * self.scale
            pygame.draw.line(self.screen, grid_color, (left, py), (right, py), 1)

    def _draw_dev_overlay(self, clock: "pygame.time.Clock") -> None:
        """Draw screen border, mouse cursor/coords, and misc dev info."""
        border_color = (0, 255, 0)
        origin_x, origin_y = self._screen_origin_px()
        pygame.draw.rect(
            self.screen,
            border_color,
            (
                origin_x + self._offset_x * self.scale,
                origin_y + self._offset_y * self.scale,
                self.width * self.scale,
                self.height * self.scale,
            ),
            1,
        )

        if self._drag_start and self._drag_current:
            x0, y0 = self._drag_start
            x1, y1 = self._drag_current
            sel_rect = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
            pygame.draw.rect(self.screen, (255, 255, 0), sel_rect, 1)

        collider_color = (0, 255, 255)
        with self._update_lock:
            collider_regions = list(self._collider_regions)
        for x, y, width, height in collider_regions:
            pygame.draw.rect(
                self.screen,
                collider_color,
                (
                    origin_x + (x + self._offset_x) * self.scale,
                    origin_y + (y + self._offset_y) * self.scale,
                    width * self.scale,
                    height * self.scale,
                ),
                1,
            )

        raw_x, raw_y = pygame.mouse.get_pos()
        log_x = (raw_x - origin_x) // self.scale - self._offset_x
        log_y = (raw_y - origin_y) // self.scale - self._offset_y
        on_screen = 0 <= log_x < self.width and 0 <= log_y < self.height

        if on_screen:
            cursor_color = (255, 0, 255)
            pygame.draw.line(self.screen, cursor_color, (raw_x - 6, raw_y), (raw_x + 6, raw_y), 1)
            pygame.draw.line(self.screen, cursor_color, (raw_x, raw_y - 6), (raw_x, raw_y + 6), 1)
            pygame.draw.circle(self.screen, cursor_color, (raw_x, raw_y), 3, 1)

        if self._dev_font is not None:
            lines = [
                f"x:{log_x} y:{log_y}",
                f"fps:{clock.get_fps():.0f}",
                f"scale:{self.scale}x  {self.width}x{self.height}",
                f"focus:{'yes' if self._window_focused else 'no'}",
                f"dirty:{'on' if self._show_debug_overlay else 'off'} "
                f"overdraw:{'on' if self._show_overdraw else 'off'} "
                f"grid:{'on' if self._show_pixel_grid else 'off'}",
            ]
            sel = self._selection_rect_logical()
            if sel:
                lines.append(f"sel x={sel[0]} y={sel[1]} w={sel[2]} h={sel[3]}")
            for i, line in enumerate(lines):
                text_surface = self._dev_font.render(line, True, (0, 255, 0), (0, 0, 0))
                self.screen.blit(text_surface, (2, 2 + i * 16))

    def _base_window_size(self) -> tuple:
        return (self._physical_width * self.scale, self._physical_height * self.scale)

    def _base_key_size(self) -> int:
        return max(8, round(self.width * self.scale * (_DEVICE_KEY_SIZE_MM / _DEVICE_SCREEN_WIDTH_MM)))

    def _base_key_gap(self) -> int:
        return max(2, round(self._base_key_size() * 0.12))

    def _screen_speaker_gap_px(self) -> int:
        return round(self.width * self.scale * (_DEVICE_SCREEN_SPEAKER_GAP_MM / _DEVICE_SCREEN_WIDTH_MM))

    def _key_top_gap_px(self) -> int:
        _, base_h = self._base_window_size()
        return round(base_h * (_DEVICE_KEY_TOP_GAP_MM / _DEVICE_SCREEN_HEIGHT_MM))

    def _bezel_px(self) -> int:
        """Chassis margin the screen/speaker sit in from -- only applied in
        device-map mode, so the normal (non-debug) window is unaffected."""
        return round(self.width * self.scale * (_DEVICE_BEZEL_MM / _DEVICE_SCREEN_WIDTH_MM))

    def _key_left_gap_px(self) -> int:
        return round(self.width * self.scale * (_DEVICE_KEY_LEFT_MM / _DEVICE_SCREEN_WIDTH_MM))

    def _screen_origin_px(self) -> tuple:
        """Where the live screen content is blitted -- (0, 0) normally, but
        inset by the chassis bezel while the device map is shown so the
        screen/speaker sit the real 3mm in from the window edge like on the
        actual device. Every overlay that draws relative to the screen (dirty
        regions, dev HUD, overdraw, pixel grid) reads this instead of
        assuming (0, 0), so they all stay aligned with wherever the screen
        actually is."""
        if self._show_device_map:
            b = self._bezel_px()
            return (b, b)
        return (0, 0)

    @staticmethod
    def _round_surface_corners(surface: "pygame.Surface", radius: int) -> "pygame.Surface":
        """Cut `surface`'s four corners to `radius` px -- a rounded-rect
        alpha mask combined via BLEND_RGBA_MIN, since surface.blit(...,
        special_flags=BLEND_RGBA_MIN) takes the per-channel minimum: the
        mask's opaque (255) interior leaves surface's real RGBA untouched,
        while its transparent (0) corners drag surface's alpha down to 0
        there, without needing to know what's underneath (device-map mode
        and the plain window fill different backgrounds behind the
        screen)."""
        rounded = surface.convert_alpha()
        mask = pygame.Surface(rounded.get_size(), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        rounded.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return rounded

    def _draw_button_shadow(self, rect: "pygame.Rect", radius: int, offset: int = 2) -> None:
        """Soft drop shadow for a keycap/button -- a rounded rect on its own
        per-pixel-alpha surface, blitted `offset` px down so only its bottom
        edge peeks past the button drawn on top of it, reading as depth
        rather than a second flat shape."""
        shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 90), shadow.get_rect(), border_radius=radius)
        self.screen.blit(shadow, (rect.x, rect.y + offset))

    def _layout_alpha_rows(self, size: int, gap: int) -> tuple:
        """Lays out the alpha block with a cascading stagger (each row indented
        further right than the last), a double-width Space key, and 1.5-width
        Shift/Enter/Fn bookending the home row, echoing the device photo's
        staggered keyboard rather than a plain uniform grid. Returns (rows,
        max_row_width); each row is [(rel_x, width, label, keycode,
        key_const), ...].

        Row 0 (Tab...Bksp) is the reference width -- it's never adjusted.
        The stagger indent (row_idx * size/2) isn't left as blank canvas in
        front of the row's first key -- that key's width absorbs it instead,
        so Shft/Fn visually fill the space the indent would otherwise leave
        empty rather than just floating a bit further right. Row 1 and row 2
        can still fall short of row 0's width after that (fewer/narrower
        remaining keys), so the same leading key absorbs whatever's left of
        the difference too, stretching to make the row match row 0's width
        instead of leaving a gap at the row's right edge."""
        rows = []
        natural_widths = []
        for row_idx, row in enumerate(_DEVICE_MAP_ALPHA_ROWS):
            row_geometry = []
            indent = 0 if row_idx == _DEVICE_MAP_NO_INDENT_ROW_INDEX else row_idx * (size // 2)
            x = 0
            for entry_idx, (label, keycode, key_const) in enumerate(row):
                if label == "Space":
                    width = size * 2 + gap
                elif label in ("Shft", "Ent", "Fn"):
                    width = round(size * 1.5)
                else:
                    width = size
                if entry_idx == 0:
                    width += indent
                row_geometry.append([x, width, label, keycode, key_const])
                x += width + gap
            if row_idx == _DEVICE_MAP_HOME_ROW_INDEX:
                # Home sits at the end of this row, in Ent's old spot.
                label, keycode, key_const = _DEVICE_MAP_HOME_KEY
                row_geometry.append([x, size, label, keycode, key_const])
                x += size + gap
            rows.append(row_geometry)
            natural_widths.append(x - gap)

        reference_width = natural_widths[0]
        for row_idx in range(1, len(rows)):
            # Applied both ways -- not just filling a shortfall (Shft/Ent's
            # case) but also shrinking back down when the leading key's
            # indent+base width already overshoots row 0 (Fn's case, once
            # its indent is absorbed above) -- every row ends flush with row
            # 0's width either way, none wider.
            deficit = reference_width - natural_widths[row_idx]
            if deficit == 0:
                continue
            row_geometry = rows[row_idx]
            row_geometry[0][1] += deficit
            for entry in row_geometry[1:]:
                entry[0] += deficit
            natural_widths[row_idx] = reference_width

        rows = [[tuple(entry) for entry in row_geometry] for row_geometry in rows]
        max_row_width = max(natural_widths)
        return rows, max_row_width

    def _controller_geometry(self, alpha_size: int, alpha_gap: int) -> tuple:
        """B/A are normal alpha-sized buttons, side by side -- that pair's
        width (2*alpha_size + alpha_gap) is also the d-pad's target width,
        since both sit in the same column. The d-pad itself is only
        2-buttons-tall (+ their padding), not 3, freeing a full row of
        height for B/A to be full alpha size instead of a shrunk-down
        controller size. Solve a d-pad cell size whose 3-cell cross (same
        span used for both its width and height) fits that target,
        keeping the same gap:size ratio the alpha keys use."""
        ratio = (alpha_gap / alpha_size) if alpha_size else 0.12
        controller_w = 2 * alpha_size + alpha_gap
        dpad_size = max(4, round(controller_w / (3 + 2 * ratio)))
        dpad_gap = max(1, round(dpad_size * ratio))
        dpad_h = 3 * dpad_size + 2 * dpad_gap
        return dpad_size, dpad_gap, controller_w, dpad_h

    def _device_map_panel_size(self) -> tuple:
        size = self._base_key_size()
        gap = self._base_key_gap()
        _, alpha_w = self._layout_alpha_rows(size, gap)
        alpha_h = len(_DEVICE_MAP_ALPHA_ROWS) * size + (len(_DEVICE_MAP_ALPHA_ROWS) - 1) * gap
        _, _, controller_w, dpad_h = self._controller_geometry(size, gap)
        controller_h = dpad_h + gap + size  # d-pad + gap + one B/A row, at alpha size
        panel_w = alpha_w + gap * 3 + controller_w
        panel_h = max(alpha_h, controller_h)
        return (panel_w, panel_h)

    def _speaker_px_width(self) -> int:
        """Blank speaker placeholder to the right of the screen, at the same
        row -- keeps the keyboard's minimum width true to the device's actual
        top-row width (screen + gap + speaker), not just the screen alone."""
        return round(self.width * self.scale * (_DEVICE_SPEAKER_WIDTH_MM / _DEVICE_SCREEN_WIDTH_MM))

    def _resize_for_device_map(self):
        base_w, base_h = self._base_window_size()
        if not self._show_device_map:
            return pygame.display.set_mode((base_w, base_h))

        bezel = self._bezel_px()
        top_row_w = bezel + base_w + self._screen_speaker_gap_px() + self._speaker_px_width() + bezel
        panel_w, panel_h = self._device_map_panel_size()
        margin = self._device_map_margin
        key_top_gap = self._key_top_gap_px()
        key_left_gap = self._key_left_gap_px()  # keyboard is 2mm from BOTH the left and right edges
        natural_total_w = panel_w + key_left_gap * 2
        min_total_w = max(natural_total_w, top_row_w)
        # If the device's true top-row width (screen + speaker, both inset by
        # the chassis bezel) or a high emulator scale is wider than the deck
        # needs, stretch the deck's height by the same ratio instead of
        # leaving it fixed -- otherwise _draw_device_map only has slack on one
        # axis and keys stay pinned at their minimum size in a top-left
        # corner of a much bigger, mostly-empty deck.
        fill_scale = max(1.0, min_total_w / natural_total_w) if natural_total_w > 0 else 1.0
        total_w = min_total_w
        total_h = bezel + base_h + key_top_gap + margin + round(panel_h * fill_scale)
        return pygame.display.set_mode((total_w, total_h))

    def _get_device_map_font(self, key_size: int):
        point_size = max(10, key_size // 3)
        font = self._device_map_font_cache.get(point_size)
        if font is None:
            font = pygame.font.SysFont("consolas", point_size)
            self._device_map_font_cache[point_size] = font
        return font

    def _draw_speaker_placeholder(self, origin_x: int, origin_y: int, base_w: int, base_h: int) -> None:
        """Dotted-grille placeholder to the right of the screen, same row,
        offset by the real screen-to-speaker gap -- keeps the deck below
        proportioned to the device's real top-row width (see
        _speaker_px_width). Used to also overlay live audio-subsystem status
        text here (debug_log.get_active_lines()) -- dropped in favor of the
        separate Voice Monitor window (View > Voice Monitor / voice_monitor.py),
        which has room to show every voice's state instead of one cramped
        line. debug_log itself is untouched; nothing currently renders its
        TTS/SFX/music/stream lines in the emulator anymore."""
        speaker_w = self._speaker_px_width()
        if speaker_w <= 0:
            return
        speaker_left = origin_x + base_w + self._screen_speaker_gap_px()
        rect = pygame.Rect(speaker_left, origin_y, speaker_w, base_h)
        pygame.draw.rect(self.screen, (32, 32, 32), rect, border_radius=2)
        pad = self.scale * 3
        inner_x = speaker_left + pad
        inner_y = origin_y + pad
        inner_w = speaker_w - 2 * pad
        inner_h = base_h - 2 * pad
        if inner_w > 0 and inner_h > 0:
            spacing = max(16, self.scale * 4)
            cols = max(1, round(inner_w / spacing))
            rows = max(1, round(inner_h / spacing))
            for row in range(rows):
                gy = inner_y + (row + 0.5) * inner_h / rows
                for col in range(cols):
                    gx = inner_x + (col + 0.5) * inner_w / cols
                    pygame.draw.circle(self.screen, (16, 16, 16), (round(gx), round(gy)), 5)

    def _draw_device_map(self) -> None:
        """Draw the TCA8418 key layout (alpha block + controller cluster) below
        the panel, echoing the device photo: a cascading key stagger, a wide
        Space key, an accented Shift key, and a fused-cross d-pad rather than
        four separate direction buttons. Keys scale up (uniformly, staying
        square) to fill whatever deck space is available instead of sitting
        pinned to their minimum top-left footprint. The screen/speaker row
        and the keyboard's left edge both sit the chassis bezel/2mm gap in
        from the window edge, matching the real device."""
        base_size = self._base_key_size()
        base_gap = self._base_key_gap()
        margin = self._device_map_margin
        key_top_gap = self._key_top_gap_px()
        key_left_gap = self._key_left_gap_px()
        bezel = self._bezel_px()
        origin_x, origin_y = self._screen_origin_px()
        base_w, base_h = self._base_window_size()
        total_w = self.screen.get_width()
        total_h = self.screen.get_height()
        keys_pressed = pygame.key.get_pressed()

        self._draw_speaker_placeholder(origin_x, origin_y, base_w, base_h)

        screen_row_bottom = origin_y + base_h
        natural_panel_w, natural_panel_h = self._device_map_panel_size()
        available_w = total_w - 2 * key_left_gap
        available_h = total_h - screen_row_bottom - key_top_gap - margin
        scale_factor = 1.0
        if natural_panel_w > 0 and natural_panel_h > 0:
            scale_factor = max(1.0, min(available_w / natural_panel_w, available_h / natural_panel_h))
        size = max(base_size, round(base_size * scale_factor))
        gap = max(base_gap, round(base_gap * scale_factor))
        font = self._get_device_map_font(size)

        key_color = (32, 32, 32)  # #202020
        key_border = (16, 16, 16)  # #101010
        controller_border = (0, 0, 0)
        highlight_color = (20, 20, 20)  # slightly darker than key_color, for pressed state
        text_color = (255, 255, 255)
        radius = max(4, size // 4)

        self._device_map_hitboxes = []

        # Live label preview: while SHIFT/FN are held (physically, or
        # latched via mouse click -- see _device_map_latched), the alpha
        # keys show the character they'll actually produce (mirrors
        # InputPackage.apply_modifier_mapping's precedence exactly, just
        # resolved here against pygame's own key state instead of the
        # keyboard-library-driven _shift_held/_fn_held in bootstrap.py,
        # since this overlay draws every frame independent of that loop).
        shift_live = (
            keys_pressed[pygame.K_LSHIFT] or keys_pressed[pygame.K_RSHIFT]
            or "KEY_LEFTSHIFT" in self._device_map_latched
        )
        fn_live = (
            keys_pressed[pygame.K_LSUPER] or keys_pressed[pygame.K_RSUPER]
            or "KEY_FN1" in self._device_map_latched
        )

        def live_label(keycode: str, fallback: str) -> str:
            if keycode not in key_map or len(fallback) != 1:
                return fallback
            if fn_live and shift_live:
                out_kc = fn_shift_key_map.get(keycode, 'KEY_FN_VOID')
            elif fn_live:
                out_kc = fn_key_map.get(keycode, keycode)
            elif shift_live:
                out_kc = shift_key_map.get(keycode, keycode)
            else:
                out_kc = keycode
            return key_map.get(out_kc, '')

        def draw_key(x, y, label, keycode, key_const, border_color, key_size, width=None):
            rect = pygame.Rect(x, y, width if width is not None else key_size, key_size)
            self._device_map_hitboxes.append((rect, keycode))
            pressed = (
                (key_const is not None and keys_pressed[key_const])
                or keycode == self._device_map_mouse_held
                or keycode in self._device_map_latched
            )
            fill_color = highlight_color if pressed else key_color
            key_radius = 2
            shadow_offset = 2
            if pressed:
                # Pressed = pushed in: no shadow to cast, and it's sunk down
                # into the space the shadow used to occupy, so the whole
                # button (fill+border+label) is drawn shadow_offset lower.
                draw_rect = rect.move(0, shadow_offset)
                border_width = 1
            else:
                draw_rect = rect
                self._draw_button_shadow(rect, key_radius, offset=shadow_offset)
                border_width = 2
            pygame.draw.rect(self.screen, fill_color, draw_rect, border_radius=key_radius)
            pygame.draw.rect(self.screen, border_color, draw_rect, border_width, border_radius=key_radius)
            text_surface = font.render(label, True, text_color)
            text_rect = text_surface.get_rect(center=draw_rect.center)
            self.screen.blit(text_surface, text_rect)

        alpha_rows, alpha_w = self._layout_alpha_rows(size, gap)
        alpha_h = len(alpha_rows) * size + (len(alpha_rows) - 1) * gap
        controller_size, controller_gap, controller_w, dpad_h = self._controller_geometry(size, gap)
        block_w = alpha_w + gap * 3 + controller_w
        block_h = max(alpha_h, dpad_h + gap + size)
        left_pad = max(0, (available_w - block_w) // 2)
        top_pad = max(0, (available_h - block_h) // 2)
        alpha_left = key_left_gap + left_pad
        top = screen_row_bottom + key_top_gap + top_pad
        
        for row_idx, row_geometry in enumerate(alpha_rows):
            y = top + row_idx * (size + gap)
            for rel_x, width, label, keycode, key_const in row_geometry:
                shown_label = live_label(keycode, label)
                draw_key(
                    alpha_left + rel_x, y, shown_label, keycode, key_const, key_border, size,
                    width=width,
                )

        controller_left = alpha_left + alpha_w + gap * 3
        # No more top Home/App row -- the d-pad starts right at `top`, sized
        # to just 2 buttons + their padding tall (see _controller_geometry),
        # with B/A sharing one full-alpha-size row below it (side by side).
        dpad_top = top
        for col_idx, (label, keycode, key_const) in enumerate(_DEVICE_MAP_BOTTOM_BUTTONS):
            x = controller_left + col_idx * (size + gap)
            y = dpad_top + dpad_h + gap
            draw_key(x, y, label, keycode, key_const, key_border, size)

        self._draw_dpad(
            controller_left, dpad_top, controller_size, controller_gap,
            key_border, highlight_color, keys_pressed, font,
        )

    def _draw_dpad(self, left, top, size, gap, border_color, highlight_color, keys_pressed, font) -> None:
        """A single fused cross (two overlapping rounded bars), not four
        separate buttons -- matches the device photo's d-pad. Drawn inset
        within its 3x3 cell footprint (like the gap between every other key)
        rather than edge-to-edge, so it doesn't read as one oversized blob
        next to the airier, gapped keyboard keys. Each arm still has its own
        FULL-cell hitbox so clicking/key state isn't penalized for the
        smaller visible shape -- but the pressed HIGHLIGHT is drawn from the
        actual inset/rounded vertical or horizontal bar (clipped to that
        arm's cell), not the raw hitbox rect, so it can't bleed past the
        cross's real edges into the background the way a plain square
        overlay did."""
        inset = max(1, size // 16)
        eff = size - 2 * inset
        span = 3 * size + 2 * gap
        vertical = pygame.Rect(left + size + gap + inset, top + inset, eff, span - 2 * inset)
        horizontal = pygame.Rect(left + inset, top + size + gap + inset, span - 2 * inset, eff)
        cross_radius = 2
        self._draw_button_shadow(vertical, cross_radius)
        self._draw_button_shadow(horizontal, cross_radius)
        pygame.draw.rect(self.screen, border_color, vertical, border_radius=cross_radius)
        pygame.draw.rect(self.screen, border_color, horizontal, border_radius=cross_radius)

        # A flash toward highlight_color reads as "pressed" here since the
        # cross's resting color is already near-black -- going darker still
        # (as the flat keys do) wouldn't be visible against it.
        pressed_color = tuple(min(255, c + 40) for c in highlight_color)
        arms = {
            "up": (pygame.Rect(left + size + gap, top, size, size), vertical),
            "down": (pygame.Rect(left + size + gap, top + 2 * (size + gap), size, size), vertical),
            "left": (pygame.Rect(left, top + size + gap, size, size), horizontal),
            "right": (pygame.Rect(left + 2 * (size + gap), top + size + gap, size, size), horizontal),
        }
        for direction, (rect, bar) in arms.items():
            _, keycode, key_const = _DPAD_KEYS[direction]
            self._device_map_hitboxes.append((rect, keycode))
            pressed = (
                (key_const is not None and keys_pressed[key_const])
                or keycode == self._device_map_mouse_held
                or keycode in self._device_map_latched
            )
            if pressed:
                self.screen.set_clip(rect)
                pygame.draw.rect(self.screen, pressed_color, bar, border_radius=cross_radius)
                self.screen.set_clip(None)

        hub_center = pygame.Rect(left + size + gap, top + size + gap, size, size).center
        pygame.draw.circle(self.screen, (20, 20, 22), hub_center, size // 5)

    def _handle_device_map_mouse_down(self, pos: tuple) -> None:
        for rect, keycode in self._device_map_hitboxes:
            if rect.collidepoint(pos):
                if keycode in _DEVICE_MAP_LATCH_KEYCODES:
                    self._toggle_device_map_latch(keycode)
                else:
                    self._device_map_mouse_held = keycode
                    if self._key_event_callback is not None:
                        self._key_event_callback(keycode, True)
                return

    def _toggle_device_map_latch(self, keycode: str) -> None:
        if keycode in self._device_map_latched:
            self._device_map_latched.discard(keycode)
            if self._key_event_callback is not None:
                self._key_event_callback(keycode, False)
        else:
            self._device_map_latched.add(keycode)
            if self._key_event_callback is not None:
                self._key_event_callback(keycode, True)

    def _handle_device_map_mouse_up(self) -> None:
        if self._device_map_mouse_held is None:
            return
        if self._key_event_callback is not None:
            self._key_event_callback(self._device_map_mouse_held, False)
        self._device_map_mouse_held = None
        # One-shot sticky keys: the key that was just released consumed
        # whatever was latched, so release the latched modifiers now too.
        if self._device_map_latched:
            for latched_keycode in list(self._device_map_latched):
                if self._key_event_callback is not None:
                    self._key_event_callback(latched_keycode, False)
            self._device_map_latched.clear()

    def is_running(self) -> bool:
        return not self._stop_event.is_set()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join()
        self._voice_monitor.close()
        pygame.quit()


__all__ = ["EmulatedDisplay"]
