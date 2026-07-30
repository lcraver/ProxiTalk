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
from PIL import Image

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

# Native Win32 menu bar (File/View/Help) command IDs
_WM_COMMAND = 0x0111
_WM_UAHDRAWMENU = 0x0091  # undocumented -- fires to paint the menu BAR background
_WM_UAHDRAWMENUITEM = 0x0092  # undocumented -- fires per top-level item (File/View/Help)
_WM_NCACTIVATE = 0x0086
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
_MF_CHECKED = 0x0008
_MF_UNCHECKED = 0x0000

_ID_FILE_RELOAD = 1001
_ID_FILE_QUIT = 1002
_ID_VIEW_DIRTY_REGIONS = 2001
_ID_VIEW_DEV_HUD = 2002
_ID_VIEW_OVERDRAW = 2003
_ID_VIEW_PIXEL_GRID = 2004
_ID_VIEW_DEVICE_MAP = 2005
_ID_HELP_README = 3001
_ID_HELP_WIKI = 3002
_ID_SCALE_1X = 4001
_ID_SCALE_2X = 4002
_ID_SCALE_4X = 4003
_ID_SCALE_8X = 4004

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

# Device control map for the debug overlay (F5) -- mirrors the TCA8418
# 6x7 matrix layout (32 alpha keys + 8 controller buttons, reusing R4-R5).
# Each entry is (label, KEY_* keycode injected on click, pygame key used only
# to light the key up live when it's pressed on the real keyboard). Fun/Home/
# App/No/Yes have no real keycode anywhere else in the codebase yet -- these
# five strings only exist because this overlay invents them; add real
# handling wherever apps should react to them before relying on it.
_DEVICE_MAP_ALPHA_ROWS = [
    [("Tab", "KEY_TAB", pygame.K_TAB), ("Q", "KEY_Q", pygame.K_q), ("W", "KEY_W", pygame.K_w),
     ("E", "KEY_E", pygame.K_e), ("R", "KEY_R", pygame.K_r), ("T", "KEY_T", pygame.K_t),
     ("Y", "KEY_Y", pygame.K_y), ("U", "KEY_U", pygame.K_u), ("I", "KEY_I", pygame.K_i),
     ("O", "KEY_O", pygame.K_o), ("P", "KEY_P", pygame.K_p), ("Bksp", "KEY_BACKSPACE", pygame.K_BACKSPACE)],
    [("Shft", "KEY_LEFTSHIFT", pygame.K_LSHIFT), ("A", "KEY_A", pygame.K_a), ("S", "KEY_S", pygame.K_s),
     ("D", "KEY_D", pygame.K_d), ("F", "KEY_F", pygame.K_f), ("G", "KEY_G", pygame.K_g),
     ("H", "KEY_H", pygame.K_h), ("J", "KEY_J", pygame.K_j), ("K", "KEY_K", pygame.K_k),
     ("L", "KEY_L", pygame.K_l)],
    [("Fn", "KEY_FUN", pygame.K_INSERT), ("Z", "KEY_Z", pygame.K_z), ("X", "KEY_X", pygame.K_x),
     ("C", "KEY_C", pygame.K_c), ("Space", "KEY_SPACE", pygame.K_SPACE), ("V", "KEY_V", pygame.K_v),
     ("B", "KEY_B", pygame.K_b), ("N", "KEY_N", pygame.K_n), ("M", "KEY_M", pygame.K_m),
     ("Ent", "KEY_ENTER", pygame.K_RETURN)],
]

# Small square buttons above/below the d-pad (drawn separately -- see
# _DPAD_KEYS below for the fused cross itself).
_DEVICE_MAP_TOP_BUTTONS = [("Home", "KEY_HOME", pygame.K_HOME), ("App", "KEY_APP", pygame.K_END)]
_DEVICE_MAP_BOTTOM_BUTTONS = [("Yes", "KEY_YES", pygame.K_PAGEUP), ("No", "KEY_NO", pygame.K_PAGEDOWN)]

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
        self._device_map_font_cache: dict = {}  # point size -> pygame.font.Font, since keys scale with window size
        self._key_event_callback: Optional[Callable[[str, bool], None]] = None

        # Native File/View/Help menu bar (Windows only)
        self._pending_menu_commands: List[int] = []
        self._wndproc_callback = None  # keeps the ctypes callback alive
        self._old_wndproc = None
        self._debug_overlays_menu = None
        self._scale_menu = None

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

        view_menu = user32.CreatePopupMenu()
        user32.AppendMenuW(view_menu, _MF_POPUP, overlays_menu, "Debug Overlays")
        user32.AppendMenuW(view_menu, _MF_POPUP, scale_menu, "Scale")

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
            return result
        return ctypes.windll.user32.CallWindowProcW(self._old_wndproc, hwnd, msg, wparam, lparam)

    def _sync_view_menu_checks(self) -> None:
        """Called after every overlay toggle (hotkey or menu click) so the
        Debug Overlays submenu's checkmarks always match reality, and the new
        state is persisted (see settings_path/_load_debug_settings) so it
        survives the next run."""
        self._save_debug_settings()
        if self._debug_overlays_menu is None:
            return
        user32 = ctypes.windll.user32
        for cmd_id, flag in (
            (_ID_VIEW_DIRTY_REGIONS, self._show_debug_overlay),
            (_ID_VIEW_DEV_HUD, self._show_dev_overlay),
            (_ID_VIEW_OVERDRAW, self._show_overdraw),
            (_ID_VIEW_PIXEL_GRID, self._show_pixel_grid),
            (_ID_VIEW_DEVICE_MAP, self._show_device_map),
        ):
            user32.CheckMenuItem(self._debug_overlays_menu, cmd_id, _MF_CHECKED if flag else _MF_UNCHECKED)

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
            elif cmd_id == _ID_HELP_README:
                webbrowser.open(README_URL)
            elif cmd_id == _ID_HELP_WIKI:
                webbrowser.open(WIKI_URL)
            elif cmd_id in (_ID_SCALE_1X, _ID_SCALE_2X, _ID_SCALE_4X, _ID_SCALE_8X):
                self.scale = {_ID_SCALE_1X: 1, _ID_SCALE_2X: 2, _ID_SCALE_4X: 4, _ID_SCALE_8X: 8}[cmd_id]
                self.screen = self._resize_for_device_map()
                self._sync_scale_menu_checks()
                continue
            else:
                continue
            self._sync_view_menu_checks()

    def _run_pygame_loop(self) -> None:
        try:
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
                "[Display] Dev keys: F1 dirty regions, F2 dev HUD (mouse/border/drag-select), "
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
                        img_rgb = img.convert("RGB")
                        data = img_rgb.tobytes()
                        last_surface = pygame.image.fromstring(data, img.size, "RGB")
                        last_surface = pygame.transform.scale(
                            last_surface, (img.size[0] * self.scale, img.size[1] * self.scale)
                        )
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
                        self.screen.fill((20, 20, 20))
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

    def _layout_alpha_rows(self, size: int, gap: int) -> tuple:
        """Lays out the alpha block with a cascading stagger (each row indented
        further right than the last) and a double-width Space key, echoing the
        device photo's staggered keyboard rather than a plain uniform grid.
        Returns (rows, max_row_width); each row is [(rel_x, width, label,
        keycode, key_const), ...]."""
        rows = []
        max_row_width = 0
        for row_idx, row in enumerate(_DEVICE_MAP_ALPHA_ROWS):
            indent = row_idx * (size // 2)
            x = indent
            row_geometry = []
            for label, keycode, key_const in row:
                width = size * 2 + gap if label == "Space" else size
                row_geometry.append((x, width, label, keycode, key_const))
                x += width + gap
            rows.append(row_geometry)
            max_row_width = max(max_row_width, x - gap)
        return rows, max_row_width

    def _controller_geometry(self, alpha_size: int, alpha_gap: int, alpha_h: int) -> tuple:
        """The controller cluster (Home/App + d-pad + Yes/No) is 5 cell-rows
        tall (top buttons, 3-row d-pad, bottom buttons) while the alpha block
        is only 3 -- reusing the alpha key size for both would make the
        controller column ~67% taller than the keyboard, leaving the shorter
        keyboard looking like it doesn't fill the deck's height. Solve for a
        smaller controller cell size so 5 controller rows == 3 alpha rows,
        keeping the same gap:size ratio the alpha keys use."""
        ratio = (alpha_gap / alpha_size) if alpha_size else 0.12
        size = max(4, round(alpha_h / (5 + 4 * ratio)))
        gap = max(1, round(size * ratio))
        return size, gap, 3 * size + 2 * gap, 5 * size + 4 * gap

    def _device_map_panel_size(self) -> tuple:
        size = self._base_key_size()
        gap = self._base_key_gap()
        _, alpha_w = self._layout_alpha_rows(size, gap)
        alpha_h = len(_DEVICE_MAP_ALPHA_ROWS) * size + (len(_DEVICE_MAP_ALPHA_ROWS) - 1) * gap
        _, _, controller_w, controller_h = self._controller_geometry(size, gap, alpha_h)
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
        """Blank dotted-grille placeholder to the right of the screen, same
        row, offset by the real screen-to-speaker gap -- purely cosmetic, but
        it's what makes the deck below actually match the device's real
        top-row width (see _speaker_px_width)."""
        speaker_w = self._speaker_px_width()
        if speaker_w <= 0:
            return
        speaker_left = origin_x + base_w + self._screen_speaker_gap_px()
        rect = pygame.Rect(speaker_left, origin_y, speaker_w, base_h)
        pygame.draw.rect(self.screen, (32, 32, 32), rect)
        spacing = max(8, self.scale * 2)
        for gy in range(origin_y + spacing // 2, origin_y + base_h, spacing):
            for gx in range(speaker_left + spacing // 2, speaker_left + speaker_w, spacing):
                pygame.draw.circle(self.screen, (0, 0, 0), (gx+1, gy+2), 3)
        pygame.draw.rect(self.screen, (0, 0, 0), rect, 1)

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

        key_color = (32, 32, 33)
        key_border = (0, 0, 0)
        accent_color = (215, 210, 225)
        controller_border = (0, 0, 0)
        highlight_color = (70, 225, 120)
        text_color = (255, 255, 255)
        radius = max(4, size // 4)

        self._device_map_hitboxes = []

        def draw_key(x, y, label, keycode, key_const, border_color, key_size, width=None, accent=False):
            rect = pygame.Rect(x, y, width if width is not None else key_size, key_size)
            self._device_map_hitboxes.append((rect, keycode))
            pressed = (key_const is not None and keys_pressed[key_const]) or (
                keycode == self._device_map_mouse_held
            )
            fill_color = highlight_color if pressed else (accent_color if accent else key_color)
            key_radius = max(3, key_size // 4)
            pygame.draw.rect(self.screen, fill_color, rect, border_radius=key_radius)
            pygame.draw.rect(self.screen, border_color, rect, max(1, key_size // 16), border_radius=key_radius)
            label_color = (0, 0, 0) if (pressed or accent) else text_color
            text_surface = font.render(label, True, label_color)
            text_rect = text_surface.get_rect(center=rect.center)
            self.screen.blit(text_surface, text_rect)

        alpha_rows, alpha_w = self._layout_alpha_rows(size, gap)
        alpha_h = len(alpha_rows) * size + (len(alpha_rows) - 1) * gap
        controller_size, controller_gap, controller_w, controller_h = self._controller_geometry(size, gap, alpha_h)
        block_w = alpha_w + gap * 3 + controller_w
        block_h = max(alpha_h, controller_h)
        left_pad = max(0, (available_w - block_w) // 2)
        top_pad = max(0, (available_h - block_h) // 2)
        alpha_left = key_left_gap + left_pad
        top = screen_row_bottom + key_top_gap + top_pad
        
        accent_labels = {
            "Shft",
            "Tab",
            "Fn",
            "Ent",
            "Bksp",
            "Space",
            
            "Yes"
        }

        for row_idx, row_geometry in enumerate(alpha_rows):
            y = top + row_idx * (size + gap)
            for rel_x, width, label, keycode, key_const in row_geometry:
                draw_key(
                    alpha_left + rel_x, y, label, keycode, key_const, key_border, size,
                    width=width, accent=label in accent_labels,
                )

        controller_left = alpha_left + alpha_w + gap * 3
        # Home/App and Yes/No stretch to fill the controller column's full
        # width (like two wide keys sharing a row) instead of sitting as
        # small squares -- only the d-pad itself stays square-cell-shaped.
        pair_width = (controller_w - controller_gap) // 2
        for col_idx, (label, keycode, key_const) in enumerate(_DEVICE_MAP_TOP_BUTTONS):
            x = controller_left + col_idx * (pair_width + controller_gap)
            draw_key(x, top, label, keycode, key_const, key_border, controller_size,
                     width=pair_width, accent=label in accent_labels)

        dpad_top = top + controller_size + controller_gap
        for col_idx, (label, keycode, key_const) in enumerate(_DEVICE_MAP_BOTTOM_BUTTONS):
            x = controller_left + col_idx * (pair_width + controller_gap)
            y = dpad_top + 3 * controller_size + 2 * controller_gap
            draw_key(x, y, label, keycode, key_const, key_border, controller_size, width=pair_width)

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
        FULL-cell hitbox/highlight so clicking/key state isn't penalized for
        the smaller visible shape."""
        inset = max(1, size // 16)
        eff = size - 2 * inset
        span = 3 * size + 2 * gap
        vertical = pygame.Rect(left + size + gap + inset, top + inset, eff, span - 2 * inset)
        horizontal = pygame.Rect(left + inset, top + size + gap + inset, span - 2 * inset, eff)
        pygame.draw.rect(self.screen, border_color, vertical, border_radius=max(2, eff // 3))
        pygame.draw.rect(self.screen, border_color, horizontal, border_radius=max(2, eff // 3))

        arms = {
            "up": pygame.Rect(left + size + gap, top, size, size),
            "down": pygame.Rect(left + size + gap, top + 2 * (size + gap), size, size),
            "left": pygame.Rect(left, top + size + gap, size, size),
            "right": pygame.Rect(left + 2 * (size + gap), top + size + gap, size, size),
        }
        for direction, rect in arms.items():
            label, keycode, key_const = _DPAD_KEYS[direction]
            self._device_map_hitboxes.append((rect, keycode))
            pressed = (key_const is not None and keys_pressed[key_const]) or (
                keycode == self._device_map_mouse_held
            )
            if pressed:
                pygame.draw.rect(self.screen, highlight_color, rect)
            label_color = (0, 0, 0) if pressed else (20, 20, 22)
            # text_surface = font.render(label, True, label_color)
            # text_rect = text_surface.get_rect(center=rect.center)
            # self.screen.blit(text_surface, text_rect)

        hub_center = pygame.Rect(left + size + gap, top + size + gap, size, size).center
        pygame.draw.circle(self.screen, (20, 20, 22), hub_center, size // 5)

    def _handle_device_map_mouse_down(self, pos: tuple) -> None:
        for rect, keycode in self._device_map_hitboxes:
            if rect.collidepoint(pos):
                self._device_map_mouse_held = keycode
                if self._key_event_callback is not None:
                    self._key_event_callback(keycode, True)
                return

    def _handle_device_map_mouse_up(self) -> None:
        if self._device_map_mouse_held is None:
            return
        if self._key_event_callback is not None:
            self._key_event_callback(self._device_map_mouse_held, False)
        self._device_map_mouse_held = None

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join()
        pygame.quit()


__all__ = ["EmulatedDisplay"]
