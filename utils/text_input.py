import bisect
from config.keymap import key_map
from utils.key_repeat import KeyRepeat


def _load_word_list(filepath):
    words = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if word:
                    words.append(word)
        words.sort()
    except Exception as e:
        print(f"[TextInput] Could not load word list {filepath}: {e}")
    return words


class TextInput:
    """Manages a text input buffer, key routing, and autocomplete.

    Basic usage (no autocomplete):
        self.text_input = TextInput(max_length=200)
        self.text_input.on_change = lambda buf, sug: self.refresh_display()
        self.text_input.on_submit = lambda buf: self.send_message(buf)
        self.text_input.on_cancel = lambda: self.exit_input_mode()

        # in onkeydown:
        self.text_input.key_down(keycode)

        # in onkeyup:
        self.text_input.key_up(keycode)

        # in update():
        self.text_input.tick()

    With autocomplete (proxi-style):
        self.text_input = TextInput.with_autocomplete(
            english_path=context["AUTOCOMPLETE_PATH"],
            japanese_path=...,   # optional
        )
        # on_change receives the current suggestion string as the second arg
        self.text_input.on_change = lambda buf, suggestion: self.refresh(buf, suggestion)

    Accept autocomplete suggestion (e.g. on TAB / ALT):
        self.text_input.accept_suggestion()
    """

    def __init__(self, max_length=200, word_list=None, japanese_word_list=None):
        self.max_length = max_length
        self._buffer = ""

        # Autocomplete word lists (sorted)
        self._word_list = word_list or []
        self._japanese_word_list = japanese_word_list or []

        # Current suggestion suffix (empty string = no suggestion)
        self.suggestion = ""

        # Callbacks — assign these before use.
        # on_change(buffer, suggestion) — called after every edit
        # on_submit(buffer)             — called on Enter with stripped text; buffer is cleared first
        # on_cancel()                   — called on ESC; buffer is cleared first
        self.on_change = None
        self.on_submit = None
        self.on_cancel = None

        # Keys that repeat when held. Backspace is on by default.
        self._repeat = KeyRepeat()
        self._repeatable_keys = {"KEY_BACKSPACE"}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def with_autocomplete(cls, english_path, japanese_path=None, max_length=200):
        """Create a TextInput pre-loaded with autocomplete word lists."""
        word_list = _load_word_list(english_path)
        japanese_word_list = _load_word_list(japanese_path) if japanese_path else []
        print(f"[TextInput] Loaded {len(word_list)} English words"
              + (f", {len(japanese_word_list)} Japanese words" if japanese_word_list else ""))
        return cls(max_length=max_length, word_list=word_list, japanese_word_list=japanese_word_list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def buffer(self):
        return self._buffer

    def clear(self):
        self._buffer = ""
        self.suggestion = ""
        self._repeat.release_all()

    def key_down(self, keycode):
        """Call from onkeydown. Fires the key immediately and registers it for repeat if applicable."""
        if keycode in self._repeatable_keys:
            self._repeat.press(keycode)
        self.handle_key(keycode)

    def key_up(self, keycode):
        """Call from onkeyup. Stops repeating the key."""
        self._repeat.release(keycode)

    def tick(self):
        """Call from update(). Fires any pending key repeats."""
        for keycode in self._repeat.tick():
            self.handle_key(keycode)

    def add_repeatable_key(self, keycode):
        """Register an additional key to repeat when held."""
        self._repeatable_keys.add(keycode)

    def handle_key(self, keycode):
        """Process a single keycode. Returns True if the key was consumed."""
        if keycode == "KEY_ESC":
            self._buffer = ""
            self.suggestion = ""
            if self.on_cancel:
                self.on_cancel()
            return True

        if keycode == "KEY_ENTER":
            text = self._buffer.strip()
            self._buffer = ""
            self.suggestion = ""
            if self.on_submit:
                self.on_submit(text)
            return True

        if keycode == "KEY_BACKSPACE":
            if self._buffer:
                self._buffer = self._buffer[:-1]
                self._update_suggestion()
                if self.on_change:
                    self.on_change(self._buffer, self.suggestion)
            return True

        if keycode in ("KEY_TAB", "KEY_RIGHTALT", "KEY_LEFTALT"):
            self.accept_suggestion()
            return True

        char = key_map.get(keycode)
        if char and len(self._buffer) < self.max_length:
            self._buffer += char
            self._update_suggestion()
            if self.on_change:
                self.on_change(self._buffer, self.suggestion)
            return True

        return False

    def accept_suggestion(self):
        """Append the current autocomplete suggestion to the buffer."""
        if self.suggestion:
            self._buffer += self.suggestion + " "
            self._update_suggestion()
            if self.on_change:
                self.on_change(self._buffer, self.suggestion)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_japanese(self):
        """Heuristic: buffer contains non-ASCII characters."""
        return any(ord(c) > 127 for c in self._buffer)

    def _update_suggestion(self):
        if not self._word_list and not self._japanese_word_list:
            self.suggestion = ""
            return
        self.suggestion = self._get_suggestion(self._buffer)

    def _get_suggestion(self, text):
        if not text or text.endswith(" "):
            return ""
        last_word = text.split(" ")[-1].lower()
        if not last_word:
            return ""

        word_list = self._japanese_word_list if (self._is_japanese() and self._japanese_word_list) else self._word_list
        i = bisect.bisect_left(word_list, last_word)
        while i < len(word_list) and word_list[i].startswith(last_word):
            suffix = word_list[i][len(last_word):]
            if suffix:
                return suffix
            i += 1
        return ""
