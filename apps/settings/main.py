"""App Settings — toggle app visibility/pinned status and system language.

A basic core_os port of V1's apps/_Settings/app_settings (which also had an
Overlays tab — dropped here since core_os has no overlays_v2 apps yet to
toggle; add one back once an overlay actually exists). Icon reused unchanged
from apps/_Settings/app_settings/icon*.png.

Uses the shared ui.TabView so this app's paged settings surface shares the
same arrow chrome and left/right transition behavior as any future tabbed
core_os app, instead of hand-rolling its own page framing and slide logic.
"""

from __future__ import annotations

import time

from core_os.apps_runtime.app_base import AppBase

_TABS = ("visibility", "pinned", "language")
_TAB_TITLE_KEYS = {
    "visibility": "app_settings.tab.visibility",
    "pinned": "app_settings.tab.pinned",
    "language": "app_settings.tab.language",
}
class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.context = context
        self.gfx = context["display_gfx"]
        self.ui = context["ui"]
        self.storage = context["storage"]
        self.apps_registry = context["apps_registry"]
        self.language = context["language"]
        self.app_control = context["app_control"]
        self.tabs = None
        self._last_update_time = None

    def start(self):
        print("[App Settings] Started")
        self._render()

    def _tab_name(self):
        return _TABS[self.tabs.current_index if self.tabs is not None else 0]

    def _tab_title(self, tab_name):
        tab_label = self.language["t"](_TAB_TITLE_KEYS[tab_name])
        prefix = self.language["t"]("app_settings.title_prefix")
        return f"{tab_label} {prefix}"

    def _entries(self):
        return [
            entry
            for entry in self.apps_registry["all"]
            if entry["metadata"].get("type", "app") != "overlay" and entry["name"] not in ("launcher", "app_settings")
        ]

    def _build_items(self, tab):
        if tab == "language":
            current = self.language["get_language"]()
            return [
                self.ui["menu_item"](self.language["t"]("language.english"), value="en", toggled=(current == "en")),
                self.ui["menu_item"](self.language["t"]("language.japanese"), value="ja", toggled=(current == "ja")),
            ]

        items = []
        for entry in self._entries():
            name = entry["name"]
            label = self.language["t"](f"apps.{name}", entry["metadata"].get("name", name))
            if tab == "visibility":
                toggled = name not in self.storage["get"]("hidden_apps", [])  # toggled box == currently visible
            else:  # pinned
                toggled = name in self.storage["get"]("pinned_apps", [])
            items.append(self.ui["menu_item"](label, value=name, toggled=toggled))
        return items

    def _build_tab_pages(self):
        return [
            {
                "title": self._tab_title(tab_name),
                "build": (lambda tab_name=tab_name: self.ui["menu"](self._build_items(tab_name), on_select=self._on_select)),
            }
            for tab_name in _TABS
        ]

    def _render(self, selected_index=None):
        if selected_index is None:
            selected_index = self.tabs.current_index if self.tabs is not None else 0
        self.tabs = self.ui["tab_view"](self._build_tab_pages(), initial_index=selected_index, font=self.gfx["fonts"]["small"])
        self.ui["layout_root"](self.tabs, margin=2)

    def _on_select(self, item):
        tab = self._tab_name()
        if tab == "language":
            if item.value != self.language["get_language"]():
                self.language["set_language"](item.value)
                self._render(selected_index=self.tabs.current_index)
            return
        if tab == "visibility":
            self._toggle_list_membership("hidden_apps", item.value)
        else:
            self._toggle_list_membership("pinned_apps", item.value)
        item.toggled = not item.toggled
        current_widget = self.tabs.current_widget
        if current_widget is not None:
            current_widget.draw()

    def _toggle_list_membership(self, key, name):
        names = self.storage["get"](key, [])
        if name in names:
            names.remove(name)
        else:
            names.append(name)
        self.storage["set"](key, names)

    def update(self):
        if self.tabs:
            now = time.monotonic()
            dt = 0.0 if self._last_update_time is None else now - self._last_update_time
            self._last_update_time = now
            self.tabs.tick(dt)

    def onkeydown(self, keycode):
        if keycode in ("KEY_LEFT", "KEY_A"):
            if self.tabs:
                self.tabs.switch(-1)
            return
        if keycode in ("KEY_RIGHT", "KEY_D"):
            if self.tabs:
                self.tabs.switch(1)
            return
        if keycode in ("KEY_ESC", "KEY_BACKSPACE"):
            self.app_control.swap_app_async("app_settings", "launcher", delay=0.1)
            return
        if self.tabs:
            self.tabs.handle_key(keycode)

    def stop(self):
        print("[App Settings] Stopped")
