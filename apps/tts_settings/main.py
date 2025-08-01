"""
TTS Settings App for ProxiTalk
Allows switching between Piper and VoiceVox TTS engines and configuring options
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from interfaces import AppBase

class App(AppBase):
    def __init__(self, context):
        super().__init__(context)
        self.name = "TTS Settings"
        self.current_engine = context["tts"]["get_engine"]()
        self.available_engines = context["tts"]["get_available_engines"]()
        self.engine_index = self.available_engines.index(self.current_engine) if self.current_engine in self.available_engines else 0
        self.voicevox_speaker_id = context["user_preferences"].get_voicevox_speaker_id()
        
        # Get VoiceVox speakers with names on startup
        self.voicevox_speakers = []
        self.voicevox_voices = []  # List of unique voices
        self.current_voice = None  # Currently selected voice
        self.current_voice_index = 0
        self.current_style_index = 0
        self.load_voicevox_speakers()
        
        # Fallback to basic speaker IDs if VoiceVox isn't available
        if not self.voicevox_speakers:
            self.speaker_ids = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]  # Common VoiceVox speaker IDs
            self.speaker_index = 0
            if self.voicevox_speaker_id in self.speaker_ids:
                self.speaker_index = self.speaker_ids.index(self.voicevox_speaker_id)
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
            self.voicevox_speakers = self.context["tts"]["get_voicevox_speakers_flat"]()
            
            if voice_data:
                self.voicevox_voices = voice_data
                print(f"[TTS Settings] Loaded {len(self.voicevox_voices)} VoiceVox voices from cache")
                total_styles = sum(len(voice['styles']) for voice in self.voicevox_voices)
                print(f"[TTS Settings] Total styles available: {total_styles}")
                
                # Debug: print first few voices and their styles
                for i, voice in enumerate(self.voicevox_voices[:2]):
                    print(f"[TTS Settings] Voice {i}: {voice['name']} ({len(voice['styles'])} styles)")
                    for j, style in enumerate(voice['styles'][:3]):
                        print(f"  Style {j}: {style['name']} (ID: {style['id']})")
            else:
                print("[TTS Settings] No VoiceVox voices available (engine may not be running)")
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
        title = "TTS Settings"
        self.context["drawing"]["draw_text_inverted"](title, 2, 2, self.context["fonts"]["small"])
        
        # Current engine info
        engine_text = f"Engine: {self.current_engine.title()}"
        self.context["drawing"]["draw_text"](engine_text, 1, 8, self.context["fonts"]["small"])
        
        # VoiceVox speaker info if applicable
        if self.current_engine == "voicevox":
            speaker_text = f"Speaker: {self.voicevox_speaker_id}"
            # Add voice and style names if available
            if self.voicevox_speakers:
                for speaker in self.voicevox_speakers:
                    if speaker['id'] == self.voicevox_speaker_id:
                        speaker_text = f"Voice: {speaker['voice']}"
                        style_text = f"Style: {speaker['style']}"
                        self.context["drawing"]["draw_text"](speaker_text, 1, 13, self.context["fonts"]["default"])
                        self.context["drawing"]["draw_text"](style_text, 1, 34, self.context["fonts"]["default"])
                        break
            else:
                self.context["drawing"]["draw_text"](speaker_text, 1, 26, self.context["fonts"]["default"])

        # Menu items
        start_y = 42 if self.current_engine == "voicevox" and self.voicevox_speakers else 38
        for i, item in enumerate(self.menu_items):
            y = start_y + i * 8
            prefix = "> " if i == self.selected_item else "  "
            text = f"{prefix}{item}"
            self.context["drawing"]["draw_text"](text, 2, y, self.context["fonts"]["small"])
    
    def draw_submenu(self):
        """Draw submenu screens"""
        self.context["drawing"]["clear_screen"]()
        
        if self.submenu_type == "engine":
            # Engine selection submenu
            title = "Select Engine"
            self.context["drawing"]["draw_text"](title, 2, 2, self.context["fonts"]["small"])
            
            start_y = 18
            for i, engine in enumerate(self.available_engines):
                y = start_y + i * 8
                prefix = "> " if i == self.engine_index else "  "
                status = " (current)" if engine == self.current_engine else ""
                text = f"{prefix}{engine.title()}{status}"
                self.context["drawing"]["draw_text"](text, 2, y, self.context["fonts"]["small"])
            
            # Instructions
            self.context["drawing"]["draw_text"]("Up/Down: Navigate", 2, 50, self.context["fonts"]["small"])
            self.context["drawing"]["draw_text"]("Enter: Select", 2, 58, self.context["fonts"]["small"])
            
        elif self.submenu_type == "voice":
            # VoiceVox voice selection submenu
            title = "Select Voice"
            self.context["drawing"]["draw_text"](title, 1, 1, self.context["fonts"]["small"])
            
            start_y = 6
            
            # Use VoiceVox voices if available, otherwise show error
            if self.voicevox_voices:
                # Display voices (limit to 5 to avoid overflow)
                display_count = min(5, len(self.voicevox_voices))
                for i in range(display_count):
                    y = start_y + i * 6
                    voice = self.voicevox_voices[i]
                    prefix = "> " if i == self.current_voice_index else "  "
                    status = " (current)" if self.current_voice and voice['name'] == self.current_voice['name'] else ""
                    text = f"{prefix}{voice['name']}{status}"
                    self.context["drawing"]["draw_text"](text, 2, y, self.context["fonts"]["small"])
                
                # Show more indicator if needed
                if len(self.voicevox_voices) > 5:
                    self.context["drawing"]["draw_text"]("...", 2, 48, self.context["fonts"]["small"])
            else:
                self.context["drawing"]["draw_text"]("VoiceVox not available", 2, 18, self.context["fonts"]["small"])
            
            # Instructions
            self.context["drawing"]["draw_text"]("Up/Down: Navigate", 2, 56, self.context["fonts"]["small"])
            self.context["drawing"]["draw_text"]("Enter: Select Style", 2, 64, self.context["fonts"]["small"])
            
        elif self.submenu_type == "style":
            # Style selection submenu for current voice
            if self.current_voice:
                title = f"{self.current_voice['name']} Styles"
                self.context["drawing"]["draw_text"](title, 2, 2, self.context["fonts"]["small"])
                
                start_y = 18
                styles = self.current_voice['styles']
                
                # Display styles (limit to 5 to avoid overflow)
                display_count = min(5, len(styles))
                for i in range(display_count):
                    y = start_y + i * 6
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
                    
                    text = f"{prefix}{style['name']}{status}"
                    self.context["drawing"]["draw_text"](text, 2, y, self.context["fonts"]["small"])
                
                # Show more indicator if needed
                if len(styles) > 5:
                    self.context["drawing"]["draw_text"]("...", 2, 48, self.context["fonts"]["small"])
                
                # Instructions
                self.context["drawing"]["draw_text"]("Up/Down: Navigate", 2, 56, self.context["fonts"]["small"])
                self.context["drawing"]["draw_text"]("Enter: Select", 2, 64, self.context["fonts"]["small"])
            else:
                self.context["drawing"]["draw_text"]("No voice selected", 2, 18, self.context["fonts"]["small"])
            
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
            self.selected_item = (self.selected_item - 1) % len(self.menu_items)
        elif key == 'KEY_DOWN':
            self.selected_item = (self.selected_item + 1) % len(self.menu_items)
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
                self.in_submenu = True
                self.submenu_type = "voice"
            elif selected_menu == "Test":
                self.test_tts()
        elif key == 'KEY_ESC':
            self.context["app_manager"].swap_app_async("tts_settings", "launcher", update_rate_hz=20.0, delay=0.1)
    
    def handle_submenu_key(self, key):
        """Handle key presses in submenus"""
        if key == 'KEY_ESC':
            if self.submenu_type == "style":
                # Go back to voice selection
                self.submenu_type = "voice"
            else:
                # Exit submenu completely
                self.in_submenu = False
                self.submenu_type = None
        elif key == 'KEY_UP':
            if self.submenu_type == "engine":
                self.engine_index = (self.engine_index - 1) % len(self.available_engines)
            elif self.submenu_type == "voice":
                if self.voicevox_voices:
                    self.current_voice_index = (self.current_voice_index - 1) % len(self.voicevox_voices)
            elif self.submenu_type == "style":
                if self.current_voice and self.current_voice['styles']:
                    self.current_style_index = (self.current_style_index - 1) % len(self.current_voice['styles'])
        elif key == 'KEY_DOWN':
            if self.submenu_type == "engine":
                self.engine_index = (self.engine_index + 1) % len(self.available_engines)
            elif self.submenu_type == "voice":
                if self.voicevox_voices:
                    self.current_voice_index = (self.current_voice_index + 1) % len(self.voicevox_voices)
            elif self.submenu_type == "style":
                if self.current_voice and self.current_voice['styles']:
                    self.current_style_index = (self.current_style_index + 1) % len(self.current_voice['styles'])
        elif key == 'KEY_ENTER':
            if self.submenu_type == "engine":
                new_engine = self.available_engines[self.engine_index]
                if new_engine != self.current_engine:
                    if self.context["tts"]["set_engine"](new_engine):
                        self.current_engine = new_engine
                        # Save preference
                        self.context["user_preferences"].set_tts_engine(new_engine)
                        
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
                        print(f"[TTS Settings] Switched to {new_engine} engine")
                    else:
                        print(f"[TTS Settings] Failed to switch to {new_engine} engine")
                self.in_submenu = False
                self.submenu_type = None
            elif self.submenu_type == "voice":
                if self.voicevox_voices and self.current_voice_index < len(self.voicevox_voices):
                    # Set current voice and enter style selection
                    self.current_voice = self.voicevox_voices[self.current_voice_index]
                    self.current_style_index = 0  # Reset to first style
                    self.submenu_type = "style"
            elif self.submenu_type == "style":
                if self.current_voice and self.current_voice['styles']:
                    # Apply the selected voice and style
                    selected_style = self.current_voice['styles'][self.current_style_index]
                    new_speaker_id = selected_style['id']
                    
                    if new_speaker_id != self.voicevox_speaker_id:
                        self.context["tts"]["set_voicevox_speaker"](new_speaker_id)
                        self.voicevox_speaker_id = new_speaker_id
                        voice_name = self.current_voice['name']
                        style_name = selected_style['name']
                        print(f"[TTS Settings] Changed VoiceVox to {voice_name} ({style_name}) - ID: {new_speaker_id}")
                    
                    # Exit submenu completely
                    self.in_submenu = False
                    self.submenu_type = None
    
    def test_tts(self):
        """Test the current TTS engine"""
        test_text = f"Testing {self.current_engine} text to speech engine."
        if self.current_engine == "voicevox":
            test_text += f" Using speaker {self.voicevox_speaker_id}."
        
        print(f"[TTS Settings] Testing {self.current_engine} TTS")
        self.context["tts"]["run"](test_text, background=False)
    
    def start(self):
        """Start the app"""
        print("[TTS Settings] App started")
        self.render()
    
    def stop(self):
        """Stop the app"""
        print("[TTS Settings] App stopped")
        super().stop()
