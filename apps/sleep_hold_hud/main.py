"""Sleep Hold HUD — always-on overlay (see bootstrap.run's start_overlay
call) that watches HOME. A short tap (released before _WARNING_DELAY_SECONDS,
i.e. before the bar ever shows) sends you to the launcher, same as every
app's own KEY_ESC handler (see apps/settings, apps/file_browser, etc.) but
from anywhere and without each app needing to wire HOME itself. Holding it
all the way to _SLEEP_HOLD_SECONDS instead calls sleep.enter_sleep(); the
fill bar appears once the hold passes _WARNING_DELAY_SECONDS so there's
visible feedback before sleep actually fires, and releasing during the bar
cancels cleanly (no partial sleep, and no launcher jump either -- once the
bar's shown, the user is clearly mid-sleep-gesture, not tapping for home).

The bar is cleared BEFORE enter_sleep() runs (not after) since sleep's
own gfx.snapshot() captures whatever's currently composited, overlay
layer included -- leaving the bar up would freeze it into the saved
frame and repaint it on wake.
"""

from __future__ import annotations

from core_os.apps_runtime.app_base import AppBase

_WARNING_DELAY_SECONDS = 2.0
_SLEEP_HOLD_SECONDS = 5.0
_FILL_SECONDS = _SLEEP_HOLD_SECONDS - _WARNING_DELAY_SECONDS

_BAR_WIDTH = 160
_BAR_HEIGHT = 10
_LABEL = "Going to sleep..."


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.gfx = context["display_gfx"]
        self.sleep = context["sleep"]
        self.app_control = context["app_control"]
        self.timers = context["timer"]["timer_manager"]()
        self.screen_width = context["screen_width"]
        self.screen_height = context["screen_height"]
        self._held = False
        self._elapsed = 0.0
        self._rect = None
        self._triggered_sleep = False

    def _show_bar(self, progress: float) -> None:
        font = self.gfx["fonts"]["small"]
        text_w, text_h = self.gfx["get_text_size"](_LABEL, font)
        width = max(_BAR_WIDTH, text_w) + 8
        height = text_h + _BAR_HEIGHT + 12
        x = (self.screen_width - width) // 2
        y = (self.screen_height - height) // 2
        rect = (x, y, width, height)
        if self._rect is not None and self._rect != rect:
            self.gfx["clear_overlay_area"](*self._rect)
        self.gfx["draw_overlay_area"](x, y, width, height, fill=255)
        self.gfx["draw_overlay_text"](_LABEL, x + (width - text_w) // 2, y + 4, font=font, fill=0)

        # Outline the trough in black, white interior, then grow a black
        # fill from the left -- NOT the reverse (white fill over a black
        # trough) which would visually read as the bar draining, not filling.
        bar_x = x + (width - _BAR_WIDTH) // 2
        bar_y = y + text_h + 8
        inset = 1
        inner_w, inner_h = _BAR_WIDTH - inset * 2, _BAR_HEIGHT - inset * 2
        self.gfx["draw_overlay_area"](bar_x, bar_y, _BAR_WIDTH, _BAR_HEIGHT, fill=0)
        self.gfx["draw_overlay_area"](bar_x + inset, bar_y + inset, inner_w, inner_h, fill=255)
        fill_w = round(inner_w * max(0.0, min(1.0, progress)))
        if fill_w > 0:
            self.gfx["draw_overlay_area"](bar_x + inset, bar_y + inset, fill_w, inner_h, fill=0)
        self._rect = rect

    def _hide_bar(self) -> None:
        if self._rect is not None:
            self.gfx["clear_overlay_area"](*self._rect)
            self._rect = None

    def onkeydown(self, keycode):
        # device_pi/input.py's key-repeat resends "down" every ~40ms while a
        # key is held, so this guard is what makes the hold a single timed
        # window instead of restarting _elapsed on every repeat.
        if keycode != "KEY_HOME" or self._held:
            return
        self._held = True
        self._elapsed = 0.0

    def onkeyup(self, keycode):
        if keycode != "KEY_HOME":
            return
        was_held = self._held
        bar_was_shown = self._rect is not None
        self._held = False
        self._elapsed = 0.0
        self._hide_bar()
        if self._triggered_sleep:
            # Release of the very key that just fired sleep -- see
            # bootstrap.py's KEY_DOWN-only wake guard for the other half of
            # this; nothing to do here except clear the flag.
            self._triggered_sleep = False
            return
        if was_held and not bar_was_shown and self.app_control.get_app_instance("launcher") is None:
            self.app_control.swap_app_async("sleep_hold_hud", "launcher", delay=0.0)

    def update(self):
        dt = self.timers.tick()
        if not self._held:
            return
        self._elapsed += dt
        if self._elapsed >= _SLEEP_HOLD_SECONDS:
            self._held = False
            self._elapsed = 0.0
            self._hide_bar()
            self._triggered_sleep = True
            self.sleep["enter_sleep"]()
            return
        if self._elapsed >= _WARNING_DELAY_SECONDS:
            progress = (self._elapsed - _WARNING_DELAY_SECONDS) / _FILL_SECONDS
            self._show_bar(progress)

    def stop(self):
        self._hide_bar()
