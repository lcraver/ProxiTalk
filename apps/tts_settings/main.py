"""
TTS Settings App for ProxiTalk
Allows switching between Piper and VoiceVox TTS engines and configuring options
"""

from interfaces import AppBase
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.name = "TTS Settings"
        self.current_engine = context["tts"]["get_engine"]()
        self.available_engines = context["tts"]["get_available_engines"]()
        self.engine_index = self.available_engines.index(
            self.current_engine) if self.current_engine in self.available_engines else 0
        self.voicevox_speaker_id = context["user_preferences"].get_voicevox_speaker_id(
        )

        # Get VoiceVox speakers with names on startup
        self.voicevox_speakers = []
        self.voicevox_voices = []  # List of unique voices
        self.current_voice = None  # Currently selected voice
        self.current_voice_index = 0
        self.current_style_index = 0

        # Scrolling support for long lists
        self.voice_scroll_offset = 0
        self.style_scroll_offset = 0
        self.max_display_items = 4  # Maximum items to show at once

        # Two-panel navigation state
        self.active_panel = "voice"  # "voice" or "style"

        self.load_voicevox_speakers()

        # Fallback to basic speaker IDs if VoiceVox isn't available
        if not self.voicevox_speakers:
            self.speaker_ids = [0, 1, 2, 3, 4, 5, 6, 7,
                                8, 9, 10]  # Common VoiceVox speaker IDs
            self.speaker_index = 0
            if self.voicevox_speaker_id in self.speaker_ids:
                self.speaker_index = self.speaker_ids.index(
                    self.voicevox_speaker_id)
        else:
            # Find current speaker in the list and determine voice/style
            self.speaker_index = 0
            for i, speaker in enumerate(self.voicevox_speakers):
                if speaker['id'] == self.voicevox_speaker_id:
                    self.speaker_index = i
                    # Find the voice and style for this speaker
                    self.find_voice_and_style_for_speaker(speaker)
                    break

        self.menu_items = ["Engine", "Test"]
        if self.current_engine == "voicevox":
            self.menu_items.insert(1, "Voice")
        self.selected_item = 0
        self.in_submenu = False
        self.submenu_type = None

    def find_voice_and_style_for_speaker(self, speaker):
        """Find the voice and style indices for a given speaker"""
        voice_name = speaker['voice']
        style_name = speaker['style']

        # Find voice index
        for i, voice in enumerate(self.voicevox_voices):
            if voice['name'] == voice_name:
                self.current_voice_index = i
                self.current_voice = voice
                break

        # Find style index within the current voice
        if self.current_voice:
            for i, style in enumerate(self.current_voice['styles']):
                if style['name'] == style_name:
                    self.current_style_index = i
                    break

    def load_voicevox_speakers(self):
        """Load VoiceVox speakers with names from the API (now cached)"""
        try:
            # Get the structured voice data (now from cache)
            voice_data = self.context["tts"]["get_voicevox_speakers"]()
            # Also get the flat list for compatibility (now from cache)
            self.voicevox_speakers = self.context["tts"]["get_voicevox_speakers_flat"](
            )

            if voice_data:
                self.voicevox_voices = voice_data
                print(
                    f"[TTS Settings] Loaded {len(self.voicevox_voices)} VoiceVox voices from cache")
                total_styles = sum(len(voice['styles'])
                                   for voice in self.voicevox_voices)
                print(f"[TTS Settings] Total styles available: {total_styles}")

                # Debug: print first few voices and their styles
                for i, voice in enumerate(self.voicevox_voices[:2]):
                    print(
                        f"[TTS Settings] Voice {i}: {voice['name']} ({len(voice['styles'])} styles)")
                    for j, style in enumerate(voice['styles'][:3]):
                        print(
                            f"  Style {j}: {style['name']} (ID: {style['id']})")
            else:
                print(
                    "[TTS Settings] No VoiceVox voices available (engine may not be running)")
                self.voicevox_voices = []
        except Exception as e:
            print(f"[TTS Settings] Failed to load VoiceVox speakers: {e}")
            self.voicevox_speakers = []
            self.voicevox_voices = []

    def update_menu_items(self):
        """Update menu items based on current engine"""
        self.menu_items = ["Engine", "Test"]
        if self.current_engine == "voicevox":
            self.menu_items.insert(1, "Voice")
        if self.selected_item >= len(self.menu_items):
            self.selected_item = len(self.menu_items) - 1

    def draw_screen(self):
        """Draw the main settings screen"""
        self.context["drawing"]["clear_screen"]()

        # Title
        width, height = self.context["drawing"]["draw_text_inverted"](
            "Engine", 2, 2, self.context["fonts"]["small"])
        self.context["drawing"]["draw_text"](
            self.current_engine.title(), width + 3, 2, self.context["fonts"]["small"])

        # VoiceVox speaker info if applicable
        if self.current_engine == "voicevox":
            speaker_text = f"Speaker: {self.voicevox_speaker_id}"
            # Add voice and style names if available
            if self.voicevox_speakers:
                for speaker in self.voicevox_speakers:
                    if speaker['id'] == self.voicevox_speaker_id:

                        # voice
                        voice_width, _ = self.context["drawing"]["draw_text_inverted"](
                            "Voice", 2, height + 4, self.context["fonts"]["small"])
                        _, voice_height = self.context["drawing"]["draw_text"](
                            speaker['voice'], width + 3, height + 3, self.context["fonts"]["default"])

                        # style
                        style_width, _ = self.context["drawing"]["draw_text_inverted"](
                            "Style", 2, height + voice_height + 6, self.context["fonts"]["small"])
                        self.context["drawing"]["draw_text"](
                            speaker['style'], width + 3, height + voice_height + 5, self.context["fonts"]["default"])
                        break
            else:
                self.context["drawing"]["draw_text"](
                    speaker_text, 1, 26, self.context["fonts"]["default"])

        # Menu items
        start_y = 42 if self.current_engine == "voicevox" and self.voicevox_speakers else 38
        for i, item in enumerate(self.menu_items):
            y = start_y + i * 8
            prefix = "> " if i == self.selected_item else "  "
            text = f"{prefix}{item}"
            self.context["drawing"]["draw_text"](
                text, 2, y, self.context["fonts"]["small"])

    def draw_submenu(self):
        """Draw submenu screens"""
        self.context["drawing"]["clear_screen"]()

        if self.submenu_type == "engine":
            # Engine selection submenu
            title = "Select Engine"
            self.context["drawing"]["draw_text"](
                title, 2, 2, self.context["fonts"]["small"])

            start_y = 18
            for i, engine in enumerate(self.available_engines):
                y = start_y + i * 8
                prefix = "> " if i == self.engine_index else "  "
                status = " (current)" if engine == self.current_engine else ""
                text = f"{prefix}{engine.title()}{status}"

                # Invert text if this is the currently selected engine
                if i == self.engine_index:
                    self.context["drawing"]["draw_text_inverted"](
                        text, 2, y, self.context["fonts"]["small"])
                else:
                    self.context["drawing"]["draw_text"](
                        text, 2, y, self.context["fonts"]["small"])

        elif self.submenu_type == "voice":
            # VoiceVox voice selection submenu

            # Title
            width, height = self.context["drawing"]["draw_text_inverted"](
                "Voice", 2, 2, self.context["fonts"]["small"])

            # Use VoiceVox voices if available, otherwise show error
            if self.voicevox_voices:
                total_voices = len(self.voicevox_voices)

                # Calculate scroll boundaries
                start_index = self.voice_scroll_offset
                end_index = min(
                    start_index + self.max_display_items, total_voices)

                # Display voices with scrolling (left half)
                for i in range(start_index, end_index):
                    display_index = i - start_index
                    y = height + 6 + display_index * 11
                    voice = self.voicevox_voices[i]
                    prefix = ""
                    status = "*" if self.current_voice and voice['name'] == self.current_voice['name'] else ""

                    # Truncate voice name if it would be too long (half screen = ~64 pixels)
                    voice_name = voice['name']
                    # Estimate character width
                    max_text_width = 64 - len(prefix) * 6 - len(status) * 6

                    # Check if we need to truncate
                    full_text = f"{prefix}{voice_name}{status}"
                    text_width, _ = self.context["get_text_size"](
                        full_text, self.context["fonts"]["default"])

                    if text_width > 55:
                        # Truncate the voice name until it fits
                        while len(voice_name) > 0:
                            truncated_text = f"{prefix}{voice_name}...{status}"
                            text_width, _ = self.context["get_text_size"](
                                truncated_text, self.context["fonts"]["default"])
                            if text_width <= 55:
                                text = truncated_text
                                break
                            voice_name = voice_name[:-1]
                        else:
                            # If even truncated to nothing, use minimal text
                            text = f"{prefix}...{status}"
                    else:
                        text = full_text

                    # Invert text if this is the currently selected voice and we're on the voice panel
                    if i == self.current_voice_index and self.active_panel == "voice":
                        width, _ = self.context["drawing"]["draw_text_inverted"](
                            text, 2, y, self.context["fonts"]["default"])
                    else:
                        width, _ = self.context["drawing"]["draw_text"](
                            text, 2, y, self.context["fonts"]["default"])

                # Draw scrollbar on the right side of left panel
                if total_voices > self.max_display_items:
                    scrollbar_x = 62
                    scrollbar_top = height + 6
                    scrollbar_bottom = height + 4 + \
                        (self.max_display_items * 11)
                    scrollbar_height = scrollbar_bottom - scrollbar_top

                    # Draw scrollbar track
                    self.context["drawing"]["draw_area"](
                        scrollbar_x+1, scrollbar_top, 1, scrollbar_height, fill=255)

                    # Calculate thumb position and size
                    thumb_height = max(
                        3, int((self.max_display_items / total_voices) * scrollbar_height))
                    thumb_position = int(
                        (start_index / (total_voices - self.max_display_items)) * (scrollbar_height - thumb_height))
                    thumb_y = scrollbar_top + thumb_position

                    # Draw scrollbar thumb
                    self.context["drawing"]["draw_area"](
                        scrollbar_x, thumb_y, 1, thumb_height, fill=255)

                # Show current voice's styles on the right side
                if self.current_voice and self.current_voice['styles']:
                    # Style panel title
                    style_title = f"{self.current_voice['name']} Styles"
                    # Truncate title if needed
                    title_width, _ = self.context["get_text_size"](
                        style_title, self.context["fonts"]["small"])
                    if title_width > 55:
                        while len(style_title) > 0:
                            truncated_title = style_title + "..."
                            title_width, _ = self.context["get_text_size"](
                                truncated_title, self.context["fonts"]["small"])
                            if title_width <= 55:
                                style_title = truncated_title
                                break
                            style_title = style_title[:-1]

                    self.context["drawing"]["draw_text_inverted"](
                        "Style", 66, 2, self.context["fonts"]["small"])

                    styles = self.current_voice['styles']
                    total_styles = len(styles)

                    # Calculate scroll boundaries for styles
                    style_start_index = self.style_scroll_offset
                    style_end_index = min(
                        style_start_index + self.max_display_items, total_styles)

                    # Display styles with scrolling (right half)
                    for i in range(style_start_index, style_end_index):
                        display_index = i - style_start_index
                        y = height + 6 + display_index * 11
                        style = styles[i]
                        prefix = ""

                        # Check if this style is currently active
                        current_speaker = None
                        for speaker in self.voicevox_speakers:
                            if speaker['id'] == self.voicevox_speaker_id:
                                current_speaker = speaker
                                break

                        status = ""
                        if current_speaker and current_speaker['style'] == style['name'] and current_speaker['voice'] == self.current_voice['name']:
                            status = " *"

                        # Truncate style name if it would be too long
                        style_name = style['name']

                        # Check if we need to truncate
                        full_text = f"{prefix}{style_name}{status}"
                        text_width, _ = self.context["get_text_size"](
                            full_text, self.context["fonts"]["default"])

                        if text_width > 60:
                            # Truncate the style name until it fits
                            while len(style_name) > 0:
                                truncated_text = f"{prefix}{style_name}...{status}"
                                text_width, _ = self.context["get_text_size"](
                                    truncated_text, self.context["fonts"]["default"])
                                if text_width <= 60:
                                    text = truncated_text
                                    break
                                style_name = style_name[:-1]
                            else:
                                # If even truncated to nothing, use minimal text
                                text = f"{prefix}...{status}"
                        else:
                            text = full_text

                        # Invert text if this is the currently selected style and we're on the style panel
                        if i == self.current_style_index and self.active_panel == "style":
                            self.context["drawing"]["draw_text_inverted"](
                                text, 66, y, self.context["fonts"]["default"])
                        else:
                            self.context["drawing"]["draw_text"](
                                text, 66, y, self.context["fonts"]["default"])

                    # Draw scrollbar for styles on the right panel
                    if total_styles > self.max_display_items:
                        scrollbar_x = 126
                        scrollbar_top = height + 6
                        scrollbar_bottom = height + 4 + \
                            (self.max_display_items * 11)
                        scrollbar_height = scrollbar_bottom - scrollbar_top

                        # Draw scrollbar track
                        self.context["drawing"]["draw_area"](
                            scrollbar_x + 1, scrollbar_top, 1, scrollbar_height, fill=255)

                        # Calculate thumb position and size
                        thumb_height = max(
                            3, int((self.max_display_items / total_styles) * scrollbar_height))
                        thumb_position = int(
                            (style_start_index / (total_styles - self.max_display_items)) * (scrollbar_height - thumb_height))
                        thumb_y = scrollbar_top + thumb_position

                        # Draw scrollbar thumb
                        self.context["drawing"]["draw_area"](
                            scrollbar_x, thumb_y, 1, thumb_height, fill=255)

                # Show current position for voices
                position_text = f"{self.current_voice_index + 1}/{total_voices}"
                self.context["drawing"]["draw_text"](
                    position_text, 1, 59, self.context["fonts"]["small"])

                # Show current position for styles if available
                if self.current_voice and self.current_voice['styles']:
                    style_position_text = f"{self.current_style_index + 1}/{len(self.current_voice['styles'])}"
                    self.context["drawing"]["draw_text"](
                        style_position_text, 66, 59, self.context["fonts"]["small"])
            else:
                self.context["drawing"]["draw_text"](
                    "VoiceVox not available", 2, 18, self.context["fonts"]["small"])
        elif self.submenu_type == "style":
            # Style selection submenu for current voice
            if self.current_voice:
                title = f"{self.current_voice['name']} Styles"
                self.context["drawing"]["draw_text"](
                    title, 2, 2, self.context["fonts"]["small"])

                start_y = 18
                styles = self.current_voice['styles']
                total_styles = len(styles)

                # Calculate scroll boundaries
                start_index = self.style_scroll_offset
                end_index = min(
                    start_index + self.max_display_items, total_styles)

                # Display styles with scrolling
                for i in range(start_index, end_index):
                    display_index = i - start_index
                    y = start_y + display_index * 6
                    style = styles[i]
                    prefix = "> " if i == self.current_style_index else "  "
                    # Check if this style is currently active
                    current_speaker = None
                    for speaker in self.voicevox_speakers:
                        if speaker['id'] == self.voicevox_speaker_id:
                            current_speaker = speaker
                            break

                    status = ""
                    if current_speaker and current_speaker['style'] == style['name']:
                        status = " (current)"

                    # Truncate style name if it would be too long (half screen = ~64 pixels)
                    style_name = style['name']

                    # Check if we need to truncate
                    full_text = f"{prefix}{style_name}{status}"
                    text_width, _ = self.context["get_text_size"](
                        full_text, self.context["fonts"]["small"])

                    if text_width > 64:
                        # Truncate the style name until it fits
                        while len(style_name) > 0:
                            truncated_text = f"{prefix}{style_name}...{status}"
                            text_width, _ = self.context["get_text_size"](
                                truncated_text, self.context["fonts"]["small"])
                            if text_width <= 64:
                                text = truncated_text
                                break
                            style_name = style_name[:-1]
                        else:
                            # If even truncated to nothing, use minimal text
                            text = f"{prefix}...{status}"
                    else:
                        text = full_text

                    # Invert text if this is the currently selected style
                    if i == self.current_style_index:
                        self.context["drawing"]["draw_text_inverted"](
                            text, 2, y, self.context["fonts"]["small"])
                    else:
                        self.context["drawing"]["draw_text"](
                            text, 2, y, self.context["fonts"]["small"])

                # Draw scrollbar on the right side
                if total_styles > self.max_display_items:
                    scrollbar_x = 120
                    scrollbar_top = start_y
                    scrollbar_bottom = start_y + \
                        (self.max_display_items - 1) * 6
                    scrollbar_height = scrollbar_bottom - scrollbar_top

                    # Draw scrollbar track
                    self.context["drawing"]["draw_area"](
                        scrollbar_x + 1, scrollbar_top, 2, scrollbar_height, fill=255)

                    # Calculate thumb position and size
                    thumb_height = max(
                        3, int((self.max_display_items / total_styles) * scrollbar_height))
                    thumb_position = int(
                        (start_index / (total_styles - self.max_display_items)) * (scrollbar_height - thumb_height))
                    thumb_y = scrollbar_top + thumb_position

                    # Draw scrollbar thumb
                    self.context["drawing"]["draw_area"](
                        scrollbar_x, thumb_y, 2, thumb_height, fill=255)

                # Show scroll indicators
                if start_index > 0:
                    self.context["drawing"]["draw_text"](
                        "↑ More", 90, start_y, self.context["fonts"]["small"])
                if end_index < total_styles:
                    self.context["drawing"]["draw_text"](
                        "↓ More", 90, start_y + (self.max_display_items - 1) * 6, self.context["fonts"]["small"])

                # Show current position
                position_text = f"{self.current_style_index + 1}/{total_styles}"
                self.context["drawing"]["draw_text"](
                    position_text, 2, 50, self.context["fonts"]["small"])

                # Instructions
                self.context["drawing"]["draw_text"](
                    "Up/Down: Navigate", 2, 56, self.context["fonts"]["small"])
                self.context["drawing"]["draw_text"](
                    "Enter: Select", 2, 64, self.context["fonts"]["small"])
            else:
                self.context["drawing"]["draw_text"](
                    "No voice selected", 2, 18, self.context["fonts"]["small"])

    def render(self):
        """Render the current screen"""
        if self.in_submenu:
            self.draw_submenu()
        else:
            self.draw_screen()

    def onkeydown(self, key):
        """Handle key press events"""
        if self.in_submenu:
            self.handle_submenu_key(key)
        else:
            self.handle_main_key(key)
        self.render()

    def handle_main_key(self, key):
        """Handle key presses in main menu"""
        if key == 'KEY_UP':
            self.selected_item = (self.selected_item -
                                  1) % len(self.menu_items)
        elif key == 'KEY_DOWN':
            self.selected_item = (self.selected_item +
                                  1) % len(self.menu_items)
        elif key == 'KEY_ENTER':
            selected_menu = self.menu_items[self.selected_item]

            if selected_menu == "Engine":
                self.in_submenu = True
                self.submenu_type = "engine"
            elif selected_menu == "Voice":
                # Use cached data, optionally refresh if needed
                if not self.voicevox_voices:
                    print("[TTS Settings] No cached voices, refreshing...")
                    self.context["tts"]["refresh_voicevox_speakers"]()
                    self.load_voicevox_speakers()
                # Reset scroll offset when entering voice selection
                self.voice_scroll_offset = 0
                self.style_scroll_offset = 0
                self.active_panel = "voice"
                self.update_voice_scroll()
                # Set current voice to show styles immediately
                if self.voicevox_voices and self.current_voice_index < len(self.voicevox_voices):
                    self.current_voice = self.voicevox_voices[self.current_voice_index]
                self.in_submenu = True
                self.submenu_type = "voice"
            elif selected_menu == "Test":
                self.test_tts()
        elif key == 'KEY_ESC':
            self.context["app_manager"].swap_app_async(
                "tts_settings", "launcher", update_rate_hz=20.0, delay=0.1)

    def update_voice_scroll(self):
        """Update voice scroll offset to keep current selection visible"""
        if not self.voicevox_voices:
            return

        # Ensure current_voice_index is within the visible range
        if self.current_voice_index < self.voice_scroll_offset:
            self.voice_scroll_offset = self.current_voice_index
        elif self.current_voice_index >= self.voice_scroll_offset + self.max_display_items:
            self.voice_scroll_offset = self.current_voice_index - self.max_display_items + 1

        # Ensure scroll offset is within bounds
        max_scroll = max(0, len(self.voicevox_voices) - self.max_display_items)
        self.voice_scroll_offset = max(
            0, min(self.voice_scroll_offset, max_scroll))

    def update_style_scroll(self):
        """Update style scroll offset to keep current selection visible"""
        if not self.current_voice or not self.current_voice['styles']:
            return

        styles = self.current_voice['styles']
        # Ensure current_style_index is within the visible range
        if self.current_style_index < self.style_scroll_offset:
            self.style_scroll_offset = self.current_style_index
        elif self.current_style_index >= self.style_scroll_offset + self.max_display_items:
            self.style_scroll_offset = self.current_style_index - self.max_display_items + 1

        # Ensure scroll offset is within bounds
        max_scroll = max(0, len(styles) - self.max_display_items)
        self.style_scroll_offset = max(
            0, min(self.style_scroll_offset, max_scroll))

    def handle_submenu_key(self, key):
        """Handle key presses in submenus"""
        if key == 'KEY_ESC':
            if self.submenu_type == "style":
                # Go back to voice selection and restore scroll position
                self.submenu_type = "voice"
                self.active_panel = "voice"
                self.update_voice_scroll()
            else:
                # Exit submenu completely
                self.in_submenu = False
                self.submenu_type = None
                self.active_panel = "voice"
        elif key == 'KEY_LEFT':
            # Switch to voice panel when in voice submenu
            if self.submenu_type == "voice":
                self.active_panel = "voice"
        elif key == 'KEY_RIGHT':
            # Switch to style panel when in voice submenu and styles are available
            if self.submenu_type == "voice" and self.current_voice and self.current_voice['styles']:
                self.active_panel = "style"
        elif key == 'KEY_UP':
            if self.submenu_type == "engine":
                self.engine_index = (self.engine_index -
                                     1) % len(self.available_engines)
            elif self.submenu_type == "voice":
                if self.active_panel == "voice" and self.voicevox_voices:
                    old_voice_index = self.current_voice_index
                    self.current_voice_index = (
                        self.current_voice_index - 1) % len(self.voicevox_voices)
                    self.update_voice_scroll()
                    # Update current voice and reset style index if voice changed
                    if self.current_voice_index != old_voice_index:
                        self.current_voice = self.voicevox_voices[self.current_voice_index]
                        self.current_style_index = 0
                        self.style_scroll_offset = 0
                        self.update_style_scroll()
                elif self.active_panel == "style" and self.current_voice and self.current_voice['styles']:
                    self.current_style_index = (
                        self.current_style_index - 1) % len(self.current_voice['styles'])
                    self.update_style_scroll()
            elif self.submenu_type == "style":
                if self.current_voice and self.current_voice['styles']:
                    self.current_style_index = (
                        self.current_style_index - 1) % len(self.current_voice['styles'])
                    self.update_style_scroll()
        elif key == 'KEY_DOWN':
            if self.submenu_type == "engine":
                self.engine_index = (self.engine_index +
                                     1) % len(self.available_engines)
            elif self.submenu_type == "voice":
                if self.active_panel == "voice" and self.voicevox_voices:
                    old_voice_index = self.current_voice_index
                    self.current_voice_index = (
                        self.current_voice_index + 1) % len(self.voicevox_voices)
                    self.update_voice_scroll()
                    # Update current voice and reset style index if voice changed
                    if self.current_voice_index != old_voice_index:
                        self.current_voice = self.voicevox_voices[self.current_voice_index]
                        self.current_style_index = 0
                        self.style_scroll_offset = 0
                        self.update_style_scroll()
                elif self.active_panel == "style" and self.current_voice and self.current_voice['styles']:
                    self.current_style_index = (
                        self.current_style_index + 1) % len(self.current_voice['styles'])
                    self.update_style_scroll()
            elif self.submenu_type == "style":
                if self.current_voice and self.current_voice['styles']:
                    self.current_style_index = (
                        self.current_style_index + 1) % len(self.current_voice['styles'])
                    self.update_style_scroll()
        elif key == 'KEY_ENTER':
            if self.submenu_type == "engine":
                new_engine = self.available_engines[self.engine_index]
                if new_engine != self.current_engine:
                    if self.context["tts"]["set_engine"](new_engine):
                        self.current_engine = new_engine
                        # Save preference
                        self.context["user_preferences"].set_tts_engine(
                            new_engine)

                        # If switching to VoiceVox, ensure cache is fresh
                        if new_engine == "voicevox":
                            # Refresh cache and reload speakers
                            self.context["tts"]["refresh_voicevox_speakers"]()
                            self.load_voicevox_speakers()
                            # Reset to first voice and style if available
                            if self.voicevox_voices:
                                self.current_voice_index = 0
                                self.current_voice = self.voicevox_voices[0]
                                self.current_style_index = 0

                        # Update menu items
                        self.update_menu_items()
                        print(
                            f"[TTS Settings] Switched to {new_engine} engine")
                    else:
                        print(
                            f"[TTS Settings] Failed to switch to {new_engine} engine")
                self.in_submenu = False
                self.submenu_type = None
                self.active_panel = "voice"
            elif self.submenu_type == "voice":
                if self.active_panel == "style" and self.current_voice and self.current_voice['styles']:
                    # Apply the selected style when ENTER is pressed on style panel
                    selected_style = self.current_voice['styles'][self.current_style_index]
                    new_speaker_id = selected_style['id']

                    if new_speaker_id != self.voicevox_speaker_id:
                        self.context["tts"]["set_voicevox_speaker"](
                            new_speaker_id)
                        self.voicevox_speaker_id = new_speaker_id
                        voice_name = self.current_voice['name']
                        style_name = selected_style['name']
                        print(
                            f"[TTS Settings] Changed VoiceVox to {voice_name} ({style_name}) - ID: {new_speaker_id}")

                    # Exit submenu completely
                    self.in_submenu = False
                    self.submenu_type = None
                    self.active_panel = "voice"
                elif self.active_panel == "voice":
                    # When ENTER is pressed on voice panel, switch to style panel
                    if self.current_voice and self.current_voice['styles']:
                        self.active_panel = "style"
            elif self.submenu_type == "style":
                if self.current_voice and self.current_voice['styles']:
                    # Apply the selected voice and style
                    selected_style = self.current_voice['styles'][self.current_style_index]
                    new_speaker_id = selected_style['id']

                    if new_speaker_id != self.voicevox_speaker_id:
                        self.context["tts"]["set_voicevox_speaker"](
                            new_speaker_id)
                        self.voicevox_speaker_id = new_speaker_id
                        voice_name = self.current_voice['name']
                        style_name = selected_style['name']
                        print(
                            f"[TTS Settings] Changed VoiceVox to {voice_name} ({style_name}) - ID: {new_speaker_id}")

                    # Exit submenu completely
                    self.in_submenu = False
                    self.submenu_type = None
                    self.active_panel = "voice"

    def test_tts(self):
        """Test the current TTS engine"""
        test_text = f"This is a test."

        if self.current_engine == "voicevox":
            test_text = "これはテストです。"

        self.context["tts"]["run"](test_text, background=True)

    def start(self):
        """Start the app"""
        print("[TTS Settings] App started")
        self.render()

    def stop(self):
        """Stop the app"""
        print("[TTS Settings] App stopped")
        super().stop()
