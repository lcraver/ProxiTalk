"""
TTS Settings App for ProxiTalk
Allows switching between Piper and VoiceVox TTS engines and configuring options
"""

from interfaces import AppBase
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class App(AppBase):
    VOICEVOX_ENGINE_ID = "voicevox"
    PIPER_ENGINE_ID = "piper"
    OPENJTALK_ENGINE_ID = "openjtalk"

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

        # Get Piper models on startup
        self.piper_models = []
        self.current_piper_model_index = 0
        self.load_piper_models()

        # Get PyOpenJTalk+ voices on startup
        self.pyopenjtalk_voices = []
        self.pyopenjtalk_grouped_voices = []
        self.current_pyopenjtalk_voice_index = 0
        self.current_pyopenjtalk_character_index = 0
        self.current_pyopenjtalk_style_index = 0
        # Scrolling for PyOpenJTalk+ interface
        self.pyopenjtalk_character_scroll_offset = 0
        self.pyopenjtalk_style_scroll_offset = 0
        # Two-panel navigation for PyOpenJTalk+
        self.pyopenjtalk_active_panel = "character"  # "character" or "style"
        self.load_pyopenjtalk_voices()

        self.menu_items = ["Engine", "Test"]
        if self.current_engine == "voicevox":
            self.menu_items.insert(1, "Voice")
        elif self.current_engine == "piper":
            self.menu_items.insert(1, "Model")
        elif self.current_engine == "openjtalk":
            self.menu_items.insert(1, "Voice")
        self.selected_item = 0
        self.in_submenu = False
        self.submenu_type = None

    # --- Generic TTS manager helpers --- #
    def _get_engine_api(self, engine_id):
        try:
            return self.context["tts"]["get_engine_api"](engine_id) or {}
        except Exception:
            return {}

    def _call_engine_api(self, method_name, *args, engine_id=None, default=None, **kwargs):
        target_engine = engine_id or self.current_engine
        api = self._get_engine_api(target_engine)
        func = api.get(method_name)
        if not func:
            return default
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            print(f"[TTS Settings] Failed to call {method_name} on {target_engine}: {exc}")
            return default

    def find_current_pyopenjtalk_voice_position(self, current_voice):
        """Find the character and style indices for current PyOpenJTalk+ voice"""
        if not current_voice or not self.pyopenjtalk_grouped_voices:
            return
        
        for char_idx, character in enumerate(self.pyopenjtalk_grouped_voices):
            for style_idx, style in enumerate(character['styles']):
                if style['filename'] == current_voice:
                    self.current_pyopenjtalk_character_index = char_idx
                    self.current_pyopenjtalk_style_index = style_idx
                    return
        
        # If not found, reset to first character and style
        self.current_pyopenjtalk_character_index = 0
        self.current_pyopenjtalk_style_index = 0

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
            voice_data = self._call_engine_api(
                "list_voices",
                engine_id=self.VOICEVOX_ENGINE_ID,
            ) or []
            flat_list = self._call_engine_api(
                "list_voice_variants",
                engine_id=self.VOICEVOX_ENGINE_ID,
            ) or []
            self.voicevox_speakers = flat_list

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

    def load_piper_models(self):
        """Load available Piper models"""
        try:
            self.piper_models = self._call_engine_api(
                "list_models",
                engine_id=self.PIPER_ENGINE_ID,
            ) or []
            current_model = self._call_engine_api(
                "get_current_model",
                engine_id=self.PIPER_ENGINE_ID,
            )
            
            if self.piper_models:
                print(f"[TTS Settings] Loaded {len(self.piper_models)} Piper models")
                
                # Find the current model index
                self.current_piper_model_index = 0
                for i, model in enumerate(self.piper_models):
                    if model['path'] == current_model:
                        self.current_piper_model_index = i
                        break
                        
                # Debug: print available models
                for i, model in enumerate(self.piper_models):
                    status = " (current)" if model['path'] == current_model else ""
                    exists = " (OK)" if model['exists'] else " (MISSING)"
                    print(f"[TTS Settings] Model {i}: {model['name']}{status}{exists}")
            else:
                print("[TTS Settings] No Piper models available")
        except Exception as e:
            print(f"[TTS Settings] Failed to load Piper models: {e}")
            self.piper_models = []

    def load_pyopenjtalk_voices(self):
        """Load available PyOpenJTalk+ voices and group them by character"""
        try:
            raw_voices = self._call_engine_api(
                "list_voices",
                engine_id=self.OPENJTALK_ENGINE_ID,
            ) or []
            current_voice = self._call_engine_api(
                "get_current_voice",
                engine_id=self.OPENJTALK_ENGINE_ID,
            )
            
            # Group voices by character name (extract character from filename)
            self.pyopenjtalk_grouped_voices = []  # List of voice groups
            self.pyopenjtalk_voices = raw_voices  # Keep original flat list for compatibility
            self.current_pyopenjtalk_character_index = 0
            self.current_pyopenjtalk_style_index = 0
            
            if raw_voices:
                print(f"[TTS Settings] Loaded {len(raw_voices)} PyOpenJTalk+ voices")
                
                # Group voices by character
                character_groups = {}
                for voice in raw_voices:
                    # Extract character name (everything before the last underscore or dash)
                    voice_name = voice['name']
                    
                    # Handle different naming patterns
                    if '_' in voice_name:
                        character = '_'.join(voice_name.split('_')[:-1])
                        style = voice_name.split('_')[-1]
                    elif '-' in voice_name:
                        parts = voice_name.split('-')
                        if len(parts) >= 2:
                            character = '-'.join(parts[:-1])
                            style = parts[-1]
                        else:
                            character = voice_name
                            style = 'default'
                    else:
                        character = voice_name
                        style = 'default'
                    
                    if character not in character_groups:
                        character_groups[character] = {
                            'name': character,
                            'styles': []
                        }
                    
                    character_groups[character]['styles'].append({
                        'name': style,
                        'filename': voice['filename'],
                        'path': voice['path'],
                        'exists': voice['exists']
                    })
                
                # Convert to list and sort
                self.pyopenjtalk_grouped_voices = list(character_groups.values())
                self.pyopenjtalk_grouped_voices.sort(key=lambda x: x['name'])
                
                # Sort styles within each character group
                for character in self.pyopenjtalk_grouped_voices:
                    character['styles'].sort(key=lambda x: x['name'])
                
                # Find current voice position in grouped structure
                self.find_current_pyopenjtalk_voice_position(current_voice)
                
                # Debug: print grouped voices
                for i, character in enumerate(self.pyopenjtalk_grouped_voices):
                    print(f"[TTS Settings] Character {i}: {character['name']} ({len(character['styles'])} styles)")
                    for j, style in enumerate(character['styles']):
                        status = " *" if style['filename'] == current_voice else ""
                        exists = " (OK)" if style['exists'] else " (MISSING)"
                        print(f"  Style {j}: {style['name']}{status}{exists}")
            else:
                print("[TTS Settings] No PyOpenJTalk+ voices available")
                self.pyopenjtalk_grouped_voices = []
        except Exception as e:
            print(f"[TTS Settings] Failed to load PyOpenJTalk+ voices: {e}")
            self.pyopenjtalk_voices = []
            self.pyopenjtalk_grouped_voices = []

    def update_menu_items(self):
        """Update menu items based on current engine"""
        self.menu_items = ["Engine", "Test"]
        if self.current_engine == "voicevox":
            self.menu_items.insert(1, "Voice")
        elif self.current_engine == "piper":
            self.menu_items.insert(1, "Model")
        elif self.current_engine == "openjtalk":
            self.menu_items.insert(1, "Voice")
        if self.selected_item >= len(self.menu_items):
            self.selected_item = len(self.menu_items) - 1

    def draw_screen(self):
        """Draw the main settings screen"""
        self.context["drawing"]["begin_batch"]()
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

        # Piper model info if applicable
        elif self.current_engine == "piper":
            current_model = self._call_engine_api("get_current_model", engine_id=self.PIPER_ENGINE_ID)
            if current_model:
                model_name = os.path.basename(current_model).replace('.onnx', '')
                model_width, _ = self.context["drawing"]["draw_text_inverted"](
                    "Model", 2, height + 4, self.context["fonts"]["small"])
                self.context["drawing"]["draw_text"](
                    model_name, width + 3, height + 3, self.context["fonts"]["default"])

        # PyOpenJTalk+ voice info if applicable
        elif self.current_engine == "openjtalk":
            current_voice = self._call_engine_api("get_current_voice", engine_id=self.OPENJTALK_ENGINE_ID)
            if current_voice:
                voice_name = current_voice.replace('.htsvoice', '')
                voice_width, _ = self.context["drawing"]["draw_text_inverted"](
                    "Voice", 2, height + 4, self.context["fonts"]["small"])
                self.context["drawing"]["draw_text"](
                    voice_name, width + 3, height + 3, self.context["fonts"]["default"])

        # Menu items
        has_info = (self.current_engine == "voicevox" and self.voicevox_speakers) or (self.current_engine == "piper") or (self.current_engine == "openjtalk")
        start_y = 42 if has_info else 38
        for i, item in enumerate(self.menu_items):
            y = start_y + i * 8
            prefix = "> " if i == self.selected_item else "  "
            text = f"{prefix}{item}"
            self.context["drawing"]["draw_text"](
                text, 2, y, self.context["fonts"]["small"])
        
        self.context["drawing"]["end_batch"]()

    def draw_submenu(self):
        """Draw submenu screens"""
        self.context["drawing"]["begin_batch"]()
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

        elif self.submenu_type == "model":
            # Piper model selection submenu
            title = "Select Model"
            self.context["drawing"]["draw_text"](
                title, 2, 2, self.context["fonts"]["small"])

            if self.piper_models:
                start_y = 18
                for i, model in enumerate(self.piper_models):
                    y = start_y + i * 8
                    prefix = "> " if i == self.current_piper_model_index else "  "
                    
                    # Show status indicators
                    status = ""
                    current_model = self._call_engine_api(
                        "get_current_model",
                        engine_id=self.PIPER_ENGINE_ID,
                    )
                    if model['path'] == current_model:
                        status += " *"
                    if not model['exists']:
                        status += " (MISSING)"
                    
                    text = f"{prefix}{model['name']}{status}"

                    # Invert text if this is the currently selected model
                    if i == self.current_piper_model_index:
                        self.context["drawing"]["draw_text_inverted"](
                            text, 2, y, self.context["fonts"]["small"])
                    else:
                        self.context["drawing"]["draw_text"](
                            text, 2, y, self.context["fonts"]["small"])
                            
                # Instructions
                self.context["drawing"]["draw_text"](
                    "Up/Down: Navigate", 2, 56, self.context["fonts"]["small"])
                self.context["drawing"]["draw_text"](
                    "Enter: Select", 2, 64, self.context["fonts"]["small"])
            else:
                self.context["drawing"]["draw_text"](
                    "No models found", 2, 18, self.context["fonts"]["small"])

        elif self.submenu_type == "pyopenjtalk_voice":
            # PyOpenJTalk+ voice selection submenu (VoiceVox-style interface)
            
            # Title
            width, height = self.context["drawing"]["draw_text_inverted"](
                "Voice", 2, 2, self.context["fonts"]["small"])

            # Use grouped voices if available, otherwise show error
            if self.pyopenjtalk_grouped_voices:
                total_characters = len(self.pyopenjtalk_grouped_voices)

                # Calculate scroll boundaries
                start_index = self.pyopenjtalk_character_scroll_offset
                end_index = min(
                    start_index + self.max_display_items, total_characters)

                # Display characters with scrolling (left half)
                for i in range(start_index, end_index):
                    display_index = i - start_index
                    y = height + 6 + display_index * 11
                    character = self.pyopenjtalk_grouped_voices[i]
                    prefix = ""
                    status = "*" if i == self.current_pyopenjtalk_character_index else ""

                    # Truncate character name if it would be too long (half screen = ~64 pixels)
                    character_name = character['name']
                    # Estimate character width
                    max_text_width = 64 - len(prefix) * 6 - len(status) * 6

                    # Check if we need to truncate
                    full_text = f"{prefix}{character_name}{status}"
                    text_width, _ = self.context["get_text_size"](
                        full_text, self.context["fonts"]["default"])

                    if text_width > 55:
                        # Truncate the character name until it fits
                        while len(character_name) > 0:
                            truncated_text = f"{prefix}{character_name}...{status}"
                            text_width, _ = self.context["get_text_size"](
                                truncated_text, self.context["fonts"]["default"])
                            if text_width <= 55:
                                text = truncated_text
                                break
                            character_name = character_name[:-1]
                        else:
                            # If even truncated to nothing, use minimal text
                            text = f"{prefix}...{status}"
                    else:
                        text = full_text

                    # Invert text if this is the currently selected character and we're on the character panel
                    if i == self.current_pyopenjtalk_character_index and self.pyopenjtalk_active_panel == "character":
                        width, _ = self.context["drawing"]["draw_text_inverted"](
                            text, 2, y, self.context["fonts"]["default"])
                    else:
                        width, _ = self.context["drawing"]["draw_text"](
                            text, 2, y, self.context["fonts"]["default"])

                # Draw scrollbar on the right side of left panel
                if total_characters > self.max_display_items:
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
                        3, int((self.max_display_items / total_characters) * scrollbar_height))
                    thumb_position = int(
                        (start_index / (total_characters - self.max_display_items)) * (scrollbar_height - thumb_height))
                    thumb_y = scrollbar_top + thumb_position

                    # Draw scrollbar thumb
                    self.context["drawing"]["draw_area"](
                        scrollbar_x, thumb_y, 1, thumb_height, fill=255)

                # Show current character's styles on the right side
                if (self.current_pyopenjtalk_character_index < len(self.pyopenjtalk_grouped_voices) and 
                    self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]['styles']):
                    
                    current_character = self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]
                    
                    # Style panel title
                    self.context["drawing"]["draw_text_inverted"](
                        "Style", 66, 2, self.context["fonts"]["small"])

                    styles = current_character['styles']
                    total_styles = len(styles)

                    # Calculate scroll boundaries for styles
                    style_start_index = self.pyopenjtalk_style_scroll_offset
                    style_end_index = min(
                        style_start_index + self.max_display_items, total_styles)

                    # Display styles with scrolling (right half)
                    for i in range(style_start_index, style_end_index):
                        display_index = i - style_start_index
                        y = height + 6 + display_index * 11
                        style = styles[i]
                        prefix = ""

                        # Check if this style is currently active
                        current_voice = self._call_engine_api(
                            "get_current_voice",
                            engine_id=self.OPENJTALK_ENGINE_ID,
                        )
                        status = ""
                        if current_voice and current_voice == style['filename']:
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
                        if i == self.current_pyopenjtalk_style_index and self.pyopenjtalk_active_panel == "style":
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

                # Show current position for characters
                position_text = f"{self.current_pyopenjtalk_character_index + 1}/{total_characters}"
                self.context["drawing"]["draw_text"](
                    position_text, 1, 59, self.context["fonts"]["small"])

                # Show current position for styles if available
                if (self.current_pyopenjtalk_character_index < len(self.pyopenjtalk_grouped_voices) and 
                    self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]['styles']):
                    style_position_text = f"{self.current_pyopenjtalk_style_index + 1}/{len(self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]['styles'])}"
                    self.context["drawing"]["draw_text"](
                        style_position_text, 66, 59, self.context["fonts"]["small"])
            else:
                self.context["drawing"]["draw_text"](
                    "No voices available", 2, 18, self.context["fonts"]["small"])
        
        self.context["drawing"]["end_batch"]()

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
        if key == 'KEY_UP' or key == 'KEY_W':
            self.selected_item = (self.selected_item -
                                  1) % len(self.menu_items)
        elif key == 'KEY_DOWN' or key == 'KEY_S':
            self.selected_item = (self.selected_item +
                                  1) % len(self.menu_items)
        elif key == 'KEY_ENTER':
            selected_menu = self.menu_items[self.selected_item]

            if selected_menu == "Engine":
                self.in_submenu = True
                self.submenu_type = "engine"
            elif selected_menu == "Voice":
                if self.current_engine == "voicevox":
                    # Use cached data, optionally refresh if needed
                    if not self.voicevox_voices:
                        print("[TTS Settings] No cached voices, refreshing...")
                        self._call_engine_api(
                            "refresh_voices",
                            engine_id=self.VOICEVOX_ENGINE_ID,
                        )
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
                elif self.current_engine == "openjtalk":
                    # Load PyOpenJTalk+ voices if needed
                    if not self.pyopenjtalk_grouped_voices:
                        print("[TTS Settings] Loading PyOpenJTalk+ voices...")
                        self.load_pyopenjtalk_voices()
                    # Reset scroll offsets when entering voice selection
                    self.pyopenjtalk_character_scroll_offset = 0
                    self.pyopenjtalk_style_scroll_offset = 0
                    self.pyopenjtalk_active_panel = "character"
                    self.update_pyopenjtalk_character_scroll()
                    self.in_submenu = True
                    self.submenu_type = "pyopenjtalk_voice"
            elif selected_menu == "Model":
                # Load Piper models if needed
                if not self.piper_models:
                    print("[TTS Settings] Loading Piper models...")
                    self.load_piper_models()
                self.in_submenu = True
                self.submenu_type = "model"
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

    def update_pyopenjtalk_character_scroll(self):
        """Update PyOpenJTalk+ character scroll offset to keep current selection visible"""
        if not self.pyopenjtalk_grouped_voices:
            return

        # Ensure current_pyopenjtalk_character_index is within the visible range
        if self.current_pyopenjtalk_character_index < self.pyopenjtalk_character_scroll_offset:
            self.pyopenjtalk_character_scroll_offset = self.current_pyopenjtalk_character_index
        elif self.current_pyopenjtalk_character_index >= self.pyopenjtalk_character_scroll_offset + self.max_display_items:
            self.pyopenjtalk_character_scroll_offset = self.current_pyopenjtalk_character_index - self.max_display_items + 1

        # Ensure scroll offset is within bounds
        max_scroll = max(0, len(self.pyopenjtalk_grouped_voices) - self.max_display_items)
        self.pyopenjtalk_character_scroll_offset = max(
            0, min(self.pyopenjtalk_character_scroll_offset, max_scroll))

    def update_pyopenjtalk_style_scroll(self):
        """Update PyOpenJTalk+ style scroll offset to keep current selection visible"""
        if (not self.pyopenjtalk_grouped_voices or 
            self.current_pyopenjtalk_character_index >= len(self.pyopenjtalk_grouped_voices)):
            return

        current_character = self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]
        styles = current_character['styles']
        
        # Ensure current_pyopenjtalk_style_index is within the visible range
        if self.current_pyopenjtalk_style_index < self.pyopenjtalk_style_scroll_offset:
            self.pyopenjtalk_style_scroll_offset = self.current_pyopenjtalk_style_index
        elif self.current_pyopenjtalk_style_index >= self.pyopenjtalk_style_scroll_offset + self.max_display_items:
            self.pyopenjtalk_style_scroll_offset = self.current_pyopenjtalk_style_index - self.max_display_items + 1

        # Ensure scroll offset is within bounds
        max_scroll = max(0, len(styles) - self.max_display_items)
        self.pyopenjtalk_style_scroll_offset = max(
            0, min(self.pyopenjtalk_style_scroll_offset, max_scroll))

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
                self.pyopenjtalk_active_panel = "character"
        elif key == 'KEY_LEFT' or key == 'KEY_A':
            # Switch to voice panel when in voice submenu, or character panel in pyopenjtalk
            if self.submenu_type == "voice":
                self.active_panel = "voice"
            elif self.submenu_type == "pyopenjtalk_voice":
                self.pyopenjtalk_active_panel = "character"
        elif key == 'KEY_RIGHT' or key == 'KEY_D':
            # Switch to style panel when styles are available
            if self.submenu_type == "voice" and self.current_voice and self.current_voice['styles']:
                self.active_panel = "style"
            elif (self.submenu_type == "pyopenjtalk_voice" and 
                  self.current_pyopenjtalk_character_index < len(self.pyopenjtalk_grouped_voices) and
                  self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]['styles']):
                self.pyopenjtalk_active_panel = "style"
        elif key == 'KEY_UP' or key == 'KEY_W':
            if self.submenu_type == "engine":
                self.engine_index = (self.engine_index -
                                     1) % len(self.available_engines)
            elif self.submenu_type == "model":
                if self.piper_models:
                    self.current_piper_model_index = (
                        self.current_piper_model_index - 1) % len(self.piper_models)
            elif self.submenu_type == "pyopenjtalk_voice":
                if self.pyopenjtalk_active_panel == "character" and self.pyopenjtalk_grouped_voices:
                    old_character_index = self.current_pyopenjtalk_character_index
                    self.current_pyopenjtalk_character_index = (
                        self.current_pyopenjtalk_character_index - 1) % len(self.pyopenjtalk_grouped_voices)
                    self.update_pyopenjtalk_character_scroll()
                    # Reset style index if character changed
                    if self.current_pyopenjtalk_character_index != old_character_index:
                        self.current_pyopenjtalk_style_index = 0
                        self.pyopenjtalk_style_scroll_offset = 0
                        self.update_pyopenjtalk_style_scroll()
                elif (self.pyopenjtalk_active_panel == "style" and 
                      self.current_pyopenjtalk_character_index < len(self.pyopenjtalk_grouped_voices) and
                      self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]['styles']):
                    current_character = self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]
                    self.current_pyopenjtalk_style_index = (
                        self.current_pyopenjtalk_style_index - 1) % len(current_character['styles'])
                    self.update_pyopenjtalk_style_scroll()
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
        elif key == 'KEY_DOWN' or key == 'KEY_S':
            if self.submenu_type == "engine":
                self.engine_index = (self.engine_index +
                                     1) % len(self.available_engines)
            elif self.submenu_type == "model":
                if self.piper_models:
                    self.current_piper_model_index = (
                        self.current_piper_model_index + 1) % len(self.piper_models)
            elif self.submenu_type == "pyopenjtalk_voice":
                if self.pyopenjtalk_active_panel == "character" and self.pyopenjtalk_grouped_voices:
                    old_character_index = self.current_pyopenjtalk_character_index
                    self.current_pyopenjtalk_character_index = (
                        self.current_pyopenjtalk_character_index + 1) % len(self.pyopenjtalk_grouped_voices)
                    self.update_pyopenjtalk_character_scroll()
                    # Reset style index if character changed
                    if self.current_pyopenjtalk_character_index != old_character_index:
                        self.current_pyopenjtalk_style_index = 0
                        self.pyopenjtalk_style_scroll_offset = 0
                        self.update_pyopenjtalk_style_scroll()
                elif (self.pyopenjtalk_active_panel == "style" and 
                      self.current_pyopenjtalk_character_index < len(self.pyopenjtalk_grouped_voices) and
                      self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]['styles']):
                    current_character = self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]
                    self.current_pyopenjtalk_style_index = (
                        self.current_pyopenjtalk_style_index + 1) % len(current_character['styles'])
                    self.update_pyopenjtalk_style_scroll()
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
                            self._call_engine_api(
                                "refresh_voices",
                                engine_id=self.VOICEVOX_ENGINE_ID,
                            )
                            self.load_voicevox_speakers()
                            # Reset to first voice and style if available
                            if self.voicevox_voices:
                                self.current_voice_index = 0
                                self.current_voice = self.voicevox_voices[0]
                                self.current_style_index = 0
                        elif new_engine == "piper":
                            # Load Piper models
                            self.load_piper_models()
                        elif new_engine == "openjtalk":
                            # Load PyOpenJTalk+ voices
                            self.load_pyopenjtalk_voices()

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
                self.pyopenjtalk_active_panel = "character"
            elif self.submenu_type == "model":
                # Apply selected Piper model
                if self.piper_models and self.current_piper_model_index < len(self.piper_models):
                    selected_model = self.piper_models[self.current_piper_model_index]
                    if selected_model['exists']:
                        if self._call_engine_api(
                            "set_model",
                            selected_model['path'],
                            engine_id=self.PIPER_ENGINE_ID,
                        ):
                            print(f"[TTS Settings] Changed Piper model to: {selected_model['name']}")
                            # Refresh the model list to update current model status
                            self.load_piper_models()
                            # Ensure preferences are explicitly saved (redundant but safe)
                            try:
                                self.context["user_preferences"].set_piper_model(selected_model['path'])
                                print(f"[TTS Settings] Saved Piper model preference: {selected_model['name']}")
                            except Exception as e:
                                print(f"[TTS Settings] Warning: Failed to save model preference: {e}")
                        else:
                            print(f"[TTS Settings] Failed to change Piper model to: {selected_model['name']}")
                    else:
                        print(f"[TTS Settings] Model file not found: {selected_model['path']}")
                
                # Exit submenu
                self.in_submenu = False
                self.submenu_type = None
            elif self.submenu_type == "pyopenjtalk_voice":
                if self.pyopenjtalk_active_panel == "style" and self.pyopenjtalk_grouped_voices:
                    # Apply the selected style when ENTER is pressed on style panel
                    current_character = self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]
                    if self.current_pyopenjtalk_style_index < len(current_character['styles']):
                        selected_style = current_character['styles'][self.current_pyopenjtalk_style_index]
                        
                        if selected_style['exists']:
                            if self._call_engine_api(
                                "set_voice",
                                selected_style['filename'],
                                engine_id=self.OPENJTALK_ENGINE_ID,
                            ):
                                print(f"[TTS Settings] Changed PyOpenJTalk+ voice to: {current_character['name']} ({selected_style['name']})")
                                # Refresh the voice list to update current voice status
                                self.load_pyopenjtalk_voices()
                                # Save preferences
                                try:
                                    self.context["user_preferences"].set_pyopenjtalk_voice(selected_style['filename'])
                                    print(f"[TTS Settings] Saved PyOpenJTalk+ voice preference: {selected_style['name']}")
                                except Exception as e:
                                    print(f"[TTS Settings] Warning: Failed to save voice preference: {e}")
                            else:
                                print(f"[TTS Settings] Failed to change PyOpenJTalk+ voice to: {selected_style['name']}")
                        else:
                            print(f"[TTS Settings] Voice file not found: {selected_style['filename']}")

                    # Exit submenu completely
                    self.in_submenu = False
                    self.submenu_type = None
                    self.pyopenjtalk_active_panel = "character"
                elif self.pyopenjtalk_active_panel == "character":
                    # When ENTER is pressed on character panel, switch to style panel
                    if (self.current_pyopenjtalk_character_index < len(self.pyopenjtalk_grouped_voices) and
                        self.pyopenjtalk_grouped_voices[self.current_pyopenjtalk_character_index]['styles']):
                        self.pyopenjtalk_active_panel = "style"
            elif self.submenu_type == "voice":
                if self.active_panel == "style" and self.current_voice and self.current_voice['styles']:
                    # Apply the selected style when ENTER is pressed on style panel
                    selected_style = self.current_voice['styles'][self.current_style_index]
                    new_speaker_id = selected_style['id']

                    if new_speaker_id != self.voicevox_speaker_id:
                        self._call_engine_api(
                            "set_voice",
                            new_speaker_id,
                            engine_id=self.VOICEVOX_ENGINE_ID,
                        )
                        self.voicevox_speaker_id = new_speaker_id
                        voice_name = self.current_voice['name']
                        style_name = selected_style['name']
                        print(
                            f"[TTS Settings] Changed VoiceVox to {voice_name} ({style_name}) - ID: {new_speaker_id}")
                        
                        # Ensure preferences are explicitly saved (redundant but safe)
                        try:
                            self.context["user_preferences"].set_voicevox_speaker_id(new_speaker_id)
                            print(f"[TTS Settings] Saved VoiceVox speaker preference: {voice_name} ({style_name})")
                        except Exception as e:
                            print(f"[TTS Settings] Warning: Failed to save speaker preference: {e}")

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
                        self._call_engine_api(
                            "set_voice",
                            new_speaker_id,
                            engine_id=self.VOICEVOX_ENGINE_ID,
                        )
                        self.voicevox_speaker_id = new_speaker_id
                        voice_name = self.current_voice['name']
                        style_name = selected_style['name']
                        print(
                            f"[TTS Settings] Changed VoiceVox to {voice_name} ({style_name}) - ID: {new_speaker_id}")
                        
                        # Ensure preferences are explicitly saved (redundant but safe)
                        try:
                            self.context["user_preferences"].set_voicevox_speaker_id(new_speaker_id)
                            print(f"[TTS Settings] Saved VoiceVox speaker preference: {voice_name} ({style_name})")
                        except Exception as e:
                            print(f"[TTS Settings] Warning: Failed to save speaker preference: {e}")

                    # Exit submenu completely
                    self.in_submenu = False
                    self.submenu_type = None
                    self.active_panel = "voice"
                    self.submenu_type = None
                    self.active_panel = "voice"

    def test_tts(self):
        """Test the current TTS engine"""
        if self.current_engine == "voicevox" or self.current_engine == "openjtalk":
            test_text = "これはテストです。"
        else:
            test_text = "This is a test."

        self.context["tts"]["run"](test_text, background=True, skip_cache=True)

    def start(self):
        """Start the app"""
        print("[TTS Settings] App started")
        self.render()

    def stop(self):
        """Stop the app"""
        print("[TTS Settings] App stopped")
        super().stop()
