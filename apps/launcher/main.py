"""Launcher — browse and launch the apps in apps/.

Simplified for this initial core_os proof-of-concept: a flat, scrollable
ui.Menu list rather than V1's icon grid + folders + pagination
(old_apps/launcher/main.py). That richer UX can return once the other ~14
V1 apps are ported into apps/ and a folder/pagination need reappears.

The Menu is unpositioned at construction and sized by a Row layout
(ui.layout_root) instead of passing explicit x/y/width/height — the same
pattern app_settings/proxi use, so adding a header or other chrome later is
just another child in the Row/Column rather than re-deriving pixel math.

App names go through the language package's t() (key "apps.<name>") so the
list flips to Japanese along with the rest of the UI.

The info panel on the right is built entirely from stock ui widgets (Row/
Column/Image/Label/TextBox) — a header row of the app's full-size icon next
to its title/version/author, with the description wrapped below — rather
than a hand-rolled widget that draws its own text/icon placement. Every
hover rebuilds this panel fresh (same reason app_settings rebuilds its Menu
per tab: these widgets don't support changing their content in place) and
slides the whole thing in via animation.doslide(), same technique
app_settings uses for its tab-switch slide -- vertically rather than
horizontally, and from whichever edge (top/bottom) matches the direction
the highlight just moved in the Menu, so the panel visually arrives from
the same direction the user is navigating.
"""

from __future__ import annotations

import os

from core_os.apps_runtime.app_base import AppBase

_SLIDE_DURATION = 0.25
_HIGHLIGHT_DURATION = 0.1
_DESCRIPTION_MAX_LINES = 4


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.context = context
        self.gfx = context["display_gfx"]
        self.apps_registry = context["apps_registry"]
        self.storage = context["storage"]
        self.ui = context["ui"]
        self.language = context["language"]
        self.app_control = context["app_control"]
        self.images = context["images"]
        self.animation = context["animation"]
        self.synth_api = context["synth"]
        self.timers = context["timer"]["timer_manager"]()
        self.screen_width = context["screen_width"]
        self.screen_height = context["screen_height"]
        self.menu = None
        self.info_panel = None
        self._panel_bounds = None
        self._info_anim = None
        self._outgoing_anim = None
        self._last_selected_index = None
        self._first_info_slide = True
        self._hover_synth = None
        self._select_synth = None

    def start(self):
        print("[Launcher] Started")
        # Short, percussive envelopes (no sustain) so hovering fast through
        # the list doesn't blur into a drone -- each blip decays well before
        # the next one can fire. Hover is a quiet high tick; select is a
        # louder, lower confirm tone so the two read as distinct UI events.
        self._hover_synth = self.synth_api["synth"](waveform="sine")
        self._hover_synth.set_adsr(0.001, 0.02, 0.0, 0.03)
        self._hover_synth.set_volume(0.35)
        self._select_synth = self.synth_api["synth"](waveform="square")
        self._select_synth.set_adsr(0.001, 0.03, 0.0, 0.05)
        self._select_synth.set_volume(0.4)
        # Noise, not a pitched waveform -- a rising-then-falling amplitude
        # swell over the same envelope the panel slide runs at is what
        # reads as "woosh" rather than a click.
        self._woosh_synth = self.synth_api["synth"](waveform="noise")
        self._woosh_synth.set_adsr(0.12, 0.1, 0.0, 0.05)
        self._woosh_synth.set_volume(0.25)
        self._build_menu()

    def _play_hover_sound(self):
        self.synth_api["play_note"](self._hover_synth, "C6", 0.03)

    def _play_select_sound(self):
        self.synth_api["play_note"](self._select_synth, "E5", 0.06)

    def _play_woosh_sound(self):
        self.synth_api["play_note"](self._woosh_synth, "A4", _SLIDE_DURATION)

    def _entries(self):
        entries = [
            entry
            for entry in self.apps_registry["all"]
            if entry["metadata"].get("type", "app") != "overlay" and entry["name"] != "launcher"
        ]
        
        # English sorts case-insensitive alphabetically. Japanese labels
        # (see each app's strings.json) are katakana/hiragana -- the
        # Unicode kana blocks are laid out in gojuon (五十音) order, the
        # same order kana keyboards/dictionaries sort by, so a plain
        # codepoint sort of the raw string already matches that system for
        # kana text. A label that's kanji instead (e.g. Settings' 設定) sorts
        # by its "apps.<name>.reading" string (kana yomi, e.g. せってい) when
        # one's recorded, falling back to the kanji itself -- codepoint
        # order for kanji doesn't track pronunciation at all, so any label
        # missing a reading still sorts wrong, but no worse than before.
        japanese = self.language["is_japanese"]()
        key = (lambda entry: self._entry_sort_label(entry)) if japanese else (
            lambda entry: self._entry_label(entry).lower()
        )
        return sorted(entries, key=key)

    def _entry_label(self, entry):
        return self.language["t"](f"apps.{entry['name']}", entry["metadata"].get("name", entry["name"]))

    def _entry_sort_label(self, entry):
        label = self._entry_label(entry)
        return self.language["t"](f"apps.{entry['name']}.reading", label)

    def _entry_description(self, entry):
        return self.language["t"](f"apps.{entry['name']}.description", entry["metadata"].get("description", ""))

    def _icon_path(self, entry):
        candidate = os.path.join(self.apps_registry["apps_dir"], entry["path"], "icon.png")
        return candidate if os.path.isfile(candidate) else None

    def _build_menu(self):
        entries = self._entries()
        items = [
            self.ui["menu_item"](self._entry_label(entry), value=entry["name"])
            for entry in entries
        ]

        self.menu = self.ui["menu"](
            items, on_select=self._on_select, on_change=self._on_hover, padding=2,
            selected_padding=2, highlight_easing="ease_in_out", highlight_settle_easing="ease_out_back",
            highlight_duration=_HIGHLIGHT_DURATION, spacing=2
        )

        last_app = self.storage["get"]("last_launched_app")
        if last_app:
            for i, entry in enumerate(entries):
                if entry["name"] == last_app:
                    self.menu.set_selected_index(i)
                    break

        # No border/fill here -- this only reserves layout space for
        # _panel_bounds before _on_hover immediately replaces it with the
        # real (bordered) panel sliding in. Giving it a border made
        # layout_root's initial draw show an empty bordered box for one
        # frame before the slide-in painted over it.
        placeholder = self.ui["column"]([], padding=2)
        root = self.ui["row"](
            [self.ui["fill"](self.menu), (placeholder, self.screen_width // 2)], spacing=2, margin=2
        )
        self.ui["layout_root"](root)
        self._panel_bounds = (placeholder.x, placeholder.y, placeholder.width, placeholder.height)
        self.info_panel = placeholder
        self._first_info_slide = True
        self._on_hover(self.menu.selected_item)

    def _build_info_panel(self, entry):
        small = self.gfx["fonts"]["small"]

        if entry is None:
            return self.ui["column"]([], border=1, padding=2, fill=True)

        icon_path = self._icon_path(entry)
        meta = entry["metadata"]
        # Spacer Labels (empty text, tagged fill()) above/below the actual
        # detail lines -- Row/Column always stretch a child to the FULL
        # cross-axis space a sibling (the icon) claims, with no built-in
        # "shrink-wrap and center" option, so vertically centering this
        # shorter text block against the taller icon needs an equal-split
        # FILL gap on both ends, the same trick CSS `margin: auto` uses.
        details = [self.ui["fill"](self.ui["label"]("", font=small))]
        details.append(self.ui["content"](self.ui["text_box"](self._entry_label(entry), font=small, max_lines=1)))
        if meta.get("author"):
            details.append(
                self.ui["content"](self.ui["text_box"](f"by {meta['author']}", font=small, max_lines=1))
            )
        details.append(self.ui["fill"](self.ui["label"]("", font=small)))

        header_children = [self.ui["fill"](self.ui["column"](details))]
        if icon_path:
            header_children.insert(0, self.ui["content"](self.ui["image"](icon_path)))
        # padding lives on the header itself (not the outer panel) so the
        # inverted flip -- which only covers this Row's OWN bounds -- picks
        # up that 2px gap too. With the padding on the outer panel instead,
        # that gap sat outside header's bounds entirely: still panel
        # background (black), never inverted, leaving an odd black moat
        # between the border and the header's white inverted box instead
        # of one seamless inverted block.
        header = self.ui["row"](header_children, spacing=3, padding=2, inverted=True)

        description = self._entry_description(entry)
        panel_children = [self.ui["content"](header)]
        if description:
            panel_children.append(
                self.ui["fill"](
                    self.ui["text_box"](
                        description, font=small, max_lines=_DESCRIPTION_MAX_LINES, padding=2
                    )
                )
            )

        return self.ui["column"](panel_children, spacing=2, border=1, fill=True)

    def _on_hover(self, item):
        # Finish whatever slide is still mid-flight before starting the
        # next one -- hovering fast (holding UP/DOWN) can retrigger this
        # well before _SLIDE_DURATION elapses, and abandoning that old
        # DoSlide outright would leave its panel frozen wherever it last
        # got to (nothing ever calls update() on it again to settle or
        # clear it), so the new slide-in would start layered over stale,
        # half-transitioned ink instead of a clean rest frame.
        if self._info_anim is not None:
            self._info_anim.finish()
        if self._outgoing_anim is not None:
            self._outgoing_anim.finish()

        entry = self.apps_registry["by_name"].get(item.value) if item else None
        panel = self._build_info_panel(entry)
        panel.set_bounds(*self._panel_bounds)

        previous_panel = self.info_panel
        self.info_panel = panel

        if self._first_info_slide:
            # Re-entering the launcher should bring the details panel in
            # from the right edge once, then hand back to the usual
            # up/down-driven vertical slide behavior for menu movement.
            self._first_info_slide = False
            self._last_selected_index = self.menu.selected_index if self.menu else 0
            self._play_woosh_sound()
            self._info_anim = self.animation["doslide"](
                panel, from_x=self.screen_width, duration=_SLIDE_DURATION, easing="ease_out_back"
            )
            self._outgoing_anim = None
        else:
            # Enter from whichever edge matches the direction the highlight
            # just moved -- pressing DOWN means the new item is further down
            # the list, so the panel arrives from off the BOTTOM edge (and
            # slides up into place); pressing UP arrives from off the TOP.
            # Falls back to "from the bottom" for same-index rebuilds. The
            # outgoing (previous) panel travels the SAME direction as the
            # incoming one -- both moving down for an UP press, both moving
            # up for a DOWN press -- so the column reads as one continuous
            # stack sliding past, not an unrelated cut.
            new_index = self.menu.selected_index if self.menu else 0
            moved_up = self._last_selected_index is not None and new_index < self._last_selected_index
            if self._last_selected_index is not None and new_index != self._last_selected_index:
                self._play_hover_sound()
            panel_height = self._panel_bounds[3]
            from_y = -panel_height if moved_up else self.screen_height
            exit_y = self.screen_height if moved_up else -panel_height
            self._last_selected_index = new_index

            if previous_panel is not None:
                prev_x, prev_y = previous_panel.x, previous_panel.y
                previous_panel.set_bounds(self._panel_bounds[0], exit_y, self._panel_bounds[2], panel_height)
                self._outgoing_anim = self.animation["doslide"](
                    previous_panel, from_x=prev_x, from_y=prev_y,
                    duration=_SLIDE_DURATION, easing="ease_out_back"
                )
            else:
                self._outgoing_anim = None

            # Built (and drawn) after the outgoing slide so the panel we're
            # heading towards paints on top of it -- ease_out_back overshoots
            # past rest, so the two can briefly overlap mid-flight, and
            # whichever draws last on a given frame wins that overlap.
            self._info_anim = self.animation["doslide"](
                panel, from_y=from_y, duration=_SLIDE_DURATION, easing="ease_out_back"
            )

    def _on_select(self, item):
        self._play_select_sound()
        self.storage["set"]("last_launched_app", item.value)
        self.app_control.swap_app_async("launcher", item.value, delay=0.1)

    def update(self):
        dt = self.timers.tick()
        if self._outgoing_anim is not None:
            self._outgoing_anim.update(dt)
            if self._outgoing_anim.done:
                self._outgoing_anim = None
        if self._info_anim is not None:
            self._info_anim.update(dt)
            if self._info_anim.done:
                self._info_anim = None
        if self.menu:
            self.menu.tick(dt)

    def onkeydown(self, keycode):
        if self.menu:
            if keycode == "KEY_NO":
                self._on_select(self.menu.selected_item)
                return
            self.menu.handle_key(keycode)

    def stop(self):
        print("[Launcher] Stopped")
