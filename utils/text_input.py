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

    def __init__(self, max_length=200, word_list=None, japanese_word_list=None, is_japanese_fn=None):
        self.max_length = max_length
        self._buffer = ""

        # Autocomplete word lists (sorted)
        self._word_list = word_list or []
        self._japanese_word_list = japanese_word_list or []

        # Which list to suggest from. Defaults to a same-as-before "does the
        # buffer contain non-ASCII" guess (for standalone/no-language-system
        # use), but callers that DO have a language setting (see
        # with_autocomplete's is_japanese_fn) should pass it in — matching
        # on buffer content alone never actually selects the Japanese list
        # in practice, since typed text is romaji (pure ASCII) right up
        # until the IME resolves it for *display*; the buffer itself never
        # gains a non-ASCII character.
        self._is_japanese_fn = is_japanese_fn

        # Current suggestion suffix (empty string = no suggestion)
        self.suggestion = ""

        # Callbacks — assign these before use.
        # on_change(buffer, suggestion) — called after every edit
        # on_submit(buffer)             — called on Enter with stripped text; buffer is cleared first
        # on_cancel()                   — called on ESC; buffer is cleared first
        self.on_change = None
        self.on_submit = None
        self.on_cancel = None

        # Cursor position: a buffer index in [0, len(buffer)]. Typed
        # characters insert here (not just append), backspace deletes the
        # character before it, and KEY_LEFT/KEY_RIGHT move it.
        self._cursor = 0

        # Keys that repeat when held. Backspace and cursor movement are on
        # by default.
        self._repeat = KeyRepeat()
        self._repeatable_keys = {"KEY_BACKSPACE", "KEY_LEFT", "KEY_RIGHT"}

        # Submit history: UP/DOWN cycle back through the last
        # HISTORY_LIMIT submitted messages, shell-history style. UP from a
        # fresh buffer stashes it as `_draft` and jumps to the most recent
        # entry; further UPs step further back; DOWN steps forward again
        # and, once past the newest entry, restores `_draft` instead of
        # wrapping around.
        self.HISTORY_LIMIT = 20
        self._history = []
        self._history_index = None
        self._draft = ""

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def with_autocomplete(cls, english_path, japanese_path=None, max_length=200, is_japanese_fn=None):
        """Create a TextInput pre-loaded with autocomplete word lists.

        is_japanese_fn, if given, is consulted on every keystroke to decide
        which single list to suggest from (see _is_japanese) — pass the
        system language setting here so English mode only ever suggests
        English words and Japanese mode only ever suggests Japanese ones,
        rather than mixing both based on buffer content."""
        word_list = _load_word_list(english_path)
        japanese_word_list = _load_word_list(japanese_path) if japanese_path else []
        print(f"[TextInput] Loaded {len(word_list)} English words"
              + (f", {len(japanese_word_list)} Japanese words" if japanese_word_list else ""))
        return cls(
            max_length=max_length,
            word_list=word_list,
            japanese_word_list=japanese_word_list,
            is_japanese_fn=is_japanese_fn,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def buffer(self):
        return self._buffer

    @property
    def cursor(self):
        return self._cursor

    def clear(self):
        self._buffer = ""
        self._cursor = 0
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
            self._cursor = 0
            self.suggestion = ""
            if self.on_cancel:
                self.on_cancel()
            return True

        if keycode == "KEY_ENTER":
            text = self._buffer.strip()
            self._record_history(text)
            self._buffer = ""
            self._cursor = 0
            self.suggestion = ""
            if self.on_submit:
                self.on_submit(text)
            return True

        if keycode == "KEY_UP":
            if not self._history:
                return False
            self._history_prev()
            return True

        if keycode == "KEY_DOWN":
            if self._history_index is None:
                return False
            self._history_next()
            return True

        if keycode == "KEY_LEFT":
            if self._cursor > 0:
                self._cursor -= 1
                self._update_suggestion()
                if self.on_change:
                    self.on_change(self._buffer, self.suggestion)
            return True

        if keycode == "KEY_RIGHT":
            if self._cursor < len(self._buffer):
                self._cursor += 1
                self._update_suggestion()
                if self.on_change:
                    self.on_change(self._buffer, self.suggestion)
            return True

        if keycode == "KEY_BACKSPACE":
            if self._cursor > 0:
                self._history_index = None
                self._buffer = self._buffer[: self._cursor - 1] + self._buffer[self._cursor :]
                self._cursor -= 1
                self._update_suggestion()
                if self.on_change:
                    self.on_change(self._buffer, self.suggestion)
            return True

        if keycode in ("KEY_TAB", "KEY_RIGHTALT", "KEY_LEFTALT"):
            self.accept_suggestion()
            return True

        char = key_map.get(keycode)
        if char and len(self._buffer) < self.max_length:
            self._history_index = None
            self._buffer = self._buffer[: self._cursor] + char + self._buffer[self._cursor :]
            self._cursor += len(char)
            self._update_suggestion()
            if self.on_change:
                self.on_change(self._buffer, self.suggestion)
            return True

        return False

    def accept_suggestion(self):
        """Append the current autocomplete suggestion to the buffer.

        Only meaningful with the cursor at the end of the buffer — that's
        the only place _update_suggestion() ever produces one, since a
        completion for text you've since moved past editing elsewhere
        wouldn't mean anything."""
        if self.suggestion and self._cursor == len(self._buffer):
            self._history_index = None
            # Japanese text typically doesn't separate words with spaces,
            # so only auto-append a trailing space for non-Japanese mode.
            trailing = "" if self._is_japanese() else " "
            self._buffer += self.suggestion + trailing
            if self._is_japanese() and self._buffer.endswith("n"):
                # Accepting a full Japanese suggestion should commit a final
                # mora now; using "nn" keeps the buffer space-free while
                # resolving display/speech to terminal ん.
                self._buffer += "n"
            self._cursor = len(self._buffer)
            self._update_suggestion()
            if self.on_change:
                self.on_change(self._buffer, self.suggestion)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _record_history(self, text):
        if not text:
            return
        self._history.append(text)
        if len(self._history) > self.HISTORY_LIMIT:
            self._history = self._history[-self.HISTORY_LIMIT:]

    def _history_prev(self):
        if self._history_index is None:
            self._draft = self._buffer
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        self._buffer = self._history[self._history_index]
        self._cursor = len(self._buffer)
        self._update_suggestion()
        if self.on_change:
            self.on_change(self._buffer, self.suggestion)

    def _history_next(self):
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._buffer = self._history[self._history_index]
        else:
            self._history_index = None
            self._buffer = self._draft
            self._draft = ""
        self._cursor = len(self._buffer)
        self._update_suggestion()
        if self.on_change:
            self.on_change(self._buffer, self.suggestion)

    def _is_japanese(self):
        """Which word list to suggest from. Prefers the caller's actual
        language setting (is_japanese_fn); falls back to a "buffer contains
        non-ASCII" guess only when no language system is wired in at all."""
        if self._is_japanese_fn is not None:
            return self._is_japanese_fn()
        return any(ord(c) > 127 for c in self._buffer)

    def _update_suggestion(self):
        # Completion only makes sense for the word you're actively typing
        # at the end of the buffer -- with the cursor parked somewhere
        # earlier (having moved it back to edit a previous spot), there's
        # no "current word" to complete.
        if (not self._word_list and not self._japanese_word_list) or self._cursor != len(self._buffer):
            self.suggestion = ""
            return
        self.suggestion = self._get_suggestion(self._buffer)

    def _get_suggestion(self, text):
        if not text or text.endswith(" "):
            return ""
        last_word = text.split(" ")[-1].lower()
        if not last_word:
            return ""

        word_list = self._japanese_word_list if self._is_japanese() else self._word_list
        i = bisect.bisect_left(word_list, last_word)
        while i < len(word_list) and word_list[i].startswith(last_word):
            suffix = word_list[i][len(last_word):]
            if suffix:
                return suffix
            i += 1
        return ""
