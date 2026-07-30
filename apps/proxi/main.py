"""Proxi — flagship TTS communicator, ported to core_os.

Typing uses ui.TextField (which wraps utils/text_input.TextInput via the
input package) instead of V1's hand-rolled cursor/segment-drawing code.
Speaking uses tts.speak_async, which deletes V1's hand-rolled
tts_queue/tts_thread/tts_worker (~75 lines) in favor of a Package-level
primitive built on Scheduler.run_background.

The typing field stays live the whole time — speaking no longer swaps to a
separate full-screen "now talking" view that blocks input. Instead a
bordered, 2-line-max ui.TextBox popup, sitting under the field, shows
what's currently being spoken — present in the layout ONLY while speaking,
and relaid-out on every _speak() call (not just the idle<->speaking
transition): the field gets its space back the instant playback ends, and
each queued message gets a box sized for ITS OWN text rather than
possibly-stale bounds left over from a longer or shorter message before it
(this box and the field share the Column's space via CONTENT/FILL sizing,
so a size mismatch there means the field's height is wrong too, not just a
cosmetic gap under the status text). Since the field keeps focus, UP/DOWN
are free for the field's own submit-history recall (see
utils/text_input.py) rather than scrolling a speech view.

TextBox itself (line-wrap/ellipsis-cap/padding/margin/border/inverted) is
a general ui.py widget, not something hand-rolled here — every font-metric
fix that went into it (line height measured against the real text rather
than a fixed reference, (n-1) inter-line gaps rather than n, ink always
starting exactly at the nominal y regardless of a font's bearing sign)
lives once in display_gfx/ui and benefits every app, instead of being
copy-pasted and re-discovered per app.

Enter while nothing is speaking starts speaking immediately, same as
before. Enter while something is *already* speaking queues the new text
instead of overlapping audio — tts.speak_async has no built-in queue of its
own, so _advance_speech_queue() drains one entry at a time as each
speak_async call's on_done fires.

CTRL toggles the system-wide language (English/Japanese) via the language
package, which also switches the active TTS engine (openjtalk <-> piper).
In Japanese mode, the typing field live-converts romaji to hiragana as you
type (language.romaji_preview, a real mora-by-mora IME parser — see
romaji_ime.py — not just a conversion applied once at the end), and the
same conversion is used for what's actually spoken.

The ready screen is built as a Column([header Row(title, hint) (CONTENT),
field (FILL), speaking status (CONTENT, only while speaking)]) via
ui.layout_root rather than hardcoded x/y — so e.g. the title's actual
height (which changes between Latin and Japanese text — misaki_gothic.ttf's
kana glyphs measure a pixel taller, see display_gfx.Package.line_height)
always pushes the content below it down by the right amount instead of a
fixed y=8/y=10. The hint shares the
title's row (title CONTENT-sized on the left, hint FILL-sized and
right-aligned within what's left) instead of its own row at the bottom.
"""

from __future__ import annotations

from core_os.apps_runtime.app_base import AppBase


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.context = context
        self.gfx = context["display_gfx"]
        self.tts = context["tts"]
        self.input = context["input"]
        self.ui = context["ui"]
        self.language = context["language"]
        self.app_control = context["app_control"]

        self.text_input = self.input["make_text_input"](is_japanese_fn=self.language["is_japanese"])
        self.text_input.on_change = self._on_change
        self.text_input.on_submit = self._on_submit

        self.field = self.ui["text_field"](
            self.text_input,
            font=self.gfx["fonts"]["small"],
            display_transform=self.language["romaji_preview"],
            valign="center",
        )
        self.speaking_label = self.ui["text_box"](max_lines=2, padding=1, border=1)
        self.speaking = False
        self._speech_queue = []

    def start(self):
        print("[Proxi] Started")
        self._render_ready()

    def _render_ready(self):
        fill, content = self.ui["fill"], self.ui["content"]
        title = self.ui["label"](self.language["t"]("proxi.title"), font=self.gfx["fonts"]["small"])
        hint = self.ui["label"](self.language["t"]("proxi.lang_hint"), font=self.gfx["fonts"]["small"], align="end")
        header = self.ui["row"]([content(title), fill(hint)])
        children = [content(header), fill(self.field)]
        if self.speaking:
            children.append(content(self.speaking_label))
        root = self.ui["column"](children, margin=4, spacing=2)
        self.ui["layout_root"](root)

    def _on_change(self, buffer, suggestion):
        pass

    def _on_submit(self, text):
        if not text:
            return
        if self.speaking:
            self._speech_queue.append(text)
        else:
            self._speak(text)

    def _speak(self, text):
        speech_text = self.language["to_speech_text"](text)

        self.speaking = True
        self.speaking_label.set_text(f"{self.language['t']('proxi.talking')}: {speech_text}")
        # Always relayout, not just on the idle->speaking transition: the
        # status box and the typing field share the Column's space via
        # CONTENT/FILL sizing, so if THIS message needs a different box
        # size than the last one did (very common between Japanese
        # messages specifically, since kana glyphs are wider per character
        # and make 2-line wraps far more common there than in English), skipping
        # the relayout left the box frozen at the previous message's
        # size — drawing a short message inside a box still sized for a
        # longer one left a visible dead gap under the text, and the
        # field's height was left just as stale.
        self._render_ready()

        def _done(_result):
            self._advance_speech_queue()

        def _error(exc):
            self.ui["toast"]().error(f"{self.language['t']('proxi.error')}: {exc}")
            print(f"[Proxi] TTS failed: {exc}")
            self._advance_speech_queue()

        self.tts["speak_async"](speech_text, on_done=_done, on_error=_error)

    def _advance_speech_queue(self):
        if self._speech_queue:
            self._speak(self._speech_queue.pop(0))
            return
        self.speaking = False
        self.speaking_label.set_text("")
        self._render_ready()  # relayout: drops the status row, field regains its space

    def update(self):
        self.text_input.tick()
        self.field.tick()

    def onkeydown(self, keycode):
        if keycode == "KEY_LEFTCTRL":
            self.language["toggle_language"]()
            self._render_ready()
            return
        if keycode == "KEY_ESC":
            self.app_control.swap_app_async("proxi", "launcher", delay=0.1)
            return
        self.field.handle_key(keycode)

    def onkeyup(self, keycode):
        pass

    def stop(self):
        print("[Proxi] Stopped")
