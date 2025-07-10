from unicodedata import name
from interfaces import AppBase
import bisect
import os
from config.keymap import key_map, shift_key_map

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.display_queue = context["display_queue"]
        self.context = context
        self.words = self.load_autocomplete_words(context["AUTOCOMPLETE_PATH"])
        self.autocomplete_words = self.load_autocomplete_words(context["AUTOCOMPLETE_PATH"])
        self.autocomplete_words.sort()
        self.currentline = ""
        
    def load_autocomplete_words(self, filepath):
        words = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip()
                    if word:
                        words.append(word)
        except Exception as e:
            print(f"Failed to load autocomplete words from {filepath}: {e}", flush=True)
        return words

    def get_autocomplete_suggestion(self, current_text):
        if not current_text or current_text.endswith(' '):
            return ""
        last_word = current_text.split(' ')[-1].lower()
        i = bisect.bisect_left(self.autocomplete_words, last_word)
        while i < len(self.autocomplete_words) and self.autocomplete_words[i].startswith(last_word):
            candidate = self.autocomplete_words[i]
            return candidate[len(last_word):]
        return ""

    def start(self):
        print("[Proxi] Started")
        # Enable cursor positioning for this app
        self._update_cursor_position = True
        self.set_screen("Ready", "Ready for input! Press [TAB] to autocomplete and [ESC] to return to launcher.")

    def update(self):
        pass
    
    def onkeyup(self, keycode):
        if keycode == 'KEY_ESC':
            self.set_screen("Launcher", "Switching to Launcher...")
            self.context["app_manager"].swap_app_async("proxi", "launcher", update_rate_hz=20.0, delay=0.1)
        
        if keycode == 'KEY_TAB':
            suggestion = self.get_autocomplete_suggestion(self.currentline)
            if suggestion:
                self.currentline += suggestion + ' '
            self.set_screen("Input", self.currentline)
            return

        char = key_map.get(keycode, None)
        if char is None:
            return

        if keycode == 'KEY_ENTER':
            old_line = self.currentline
            self.context["run_tts"](self.currentline)
            cached_path = os.path.join(self.context["CACHE_DIR"], self.context["hash_text"](old_line) + ".raw")
            if os.path.exists(cached_path):
                self.currentline = ""
                self.set_screen("Ready", "Text spoken! Ready for [new input]...")
            else:
                self.set_screen("Input", old_line)
        elif keycode == 'KEY_BACKSPACE':
            self.currentline = self.currentline[:-1]
            self.set_screen("Input", self.currentline)
        else:
            self.currentline += char
            suggestion = self.get_autocomplete_suggestion(self.currentline)
            if not suggestion:
                self.set_screen("Input", self.currentline)
            else:
                # Create custom display with suggestion background
                self.set_screen("Input", self.currentline + f"[{suggestion}]")
    
    def stop(self):
        print("[Proxi] Stopped")
