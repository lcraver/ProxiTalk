"""
User preferences management for ProxiTalk
Handles storing and retrieving user settings like last launched app
"""

import json
import os
from typing import Optional, Dict, Any

class UserPreferences:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.preferences_file = os.path.join(config_dir, "user_preferences.json")
        self._preferences = self._load_preferences()
    
    def _load_preferences(self) -> Dict[str, Any]:
        """Load preferences from JSON file, create default if not exists"""
        if os.path.exists(self.preferences_file):
            try:
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Preferences] Error loading preferences: {e}")
                return self._get_default_preferences()
        else:
            return self._get_default_preferences()
    
    def _get_default_preferences(self) -> Dict[str, Any]:
        """Return default preferences"""
        return {
            "last_launched_app": None,
            "launcher_selection": 0,
            "hidden_apps": [],
            "pinned_apps": [],
            "disabled_overlays": [],
            "tts_engine": "piper",  # Default TTS engine: "piper", "voicevox", or "openjtalk"
            "disabled_tts_engines": [],  # Engines to hide even if installed
            "voicevox_speaker_id": 2,  # Default VoiceVox speaker ID
            "piper_model": None,  # Default Piper model path
            "pyopenjtalk_voice": None,  # Default PyOpenJTalk+ voice filename
            "keyboard_device_path": None,  # Optional override for /dev/input/eventX
            "auto_sleep_minutes": 5,  # Minutes of inactivity before sleep (0 disables)
            "debug_piper_wav": False,  # Write .wav files alongside .raw cache entries for debugging
        }
    
    def _save_preferences(self) -> bool:
        """Save preferences to JSON file"""
        try:
            # Ensure config directory exists
            os.makedirs(self.config_dir, exist_ok=True)
            
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(self._preferences, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"[Preferences] Error saving preferences: {e}")
            return False
    
    def get_last_launched_app(self) -> Optional[str]:
        """Get the name of the last launched app"""
        return self._preferences.get("last_launched_app")
    
    def set_last_launched_app(self, app_name: str) -> bool:
        """Set the last launched app name"""
        self._preferences["last_launched_app"] = app_name
        return self._save_preferences()
    
    def get_launcher_selection(self) -> int:
        """Get the last launcher selection index"""
        return self._preferences.get("launcher_selection", 0)
    
    def set_launcher_selection(self, selection: int) -> bool:
        """Set the launcher selection index"""
        self._preferences["launcher_selection"] = selection
        return self._save_preferences()
    
    def get_preference(self, key: str, default=None) -> Any:
        """Get any preference value"""
        return self._preferences.get(key, default)
    
    def set_preference(self, key: str, value: Any) -> bool:
        """Set any preference value"""
        self._preferences[key] = value
        return self._save_preferences()
    
    def get_hidden_apps(self) -> list:
        """Get list of hidden app names"""
        return self._preferences.get("hidden_apps", [])
    
    def is_app_hidden(self, app_name: str) -> bool:
        """Check if an app is hidden"""
        hidden_apps = self.get_hidden_apps()
        return app_name in hidden_apps
    
    def hide_app(self, app_name: str) -> bool:
        """Hide an app from the launcher"""
        hidden_apps = self.get_hidden_apps()
        if app_name not in hidden_apps:
            hidden_apps.append(app_name)
            self._preferences["hidden_apps"] = hidden_apps
            return self._save_preferences()
        return True  # Already hidden
    
    def unhide_app(self, app_name: str) -> bool:
        """Unhide an app from the launcher"""
        hidden_apps = self.get_hidden_apps()
        if app_name in hidden_apps:
            hidden_apps.remove(app_name)
            self._preferences["hidden_apps"] = hidden_apps
            return self._save_preferences()
        return True  # Already visible
    
    def toggle_app_visibility(self, app_name: str) -> bool:
        """Toggle app visibility in the launcher"""
        if self.is_app_hidden(app_name):
            return self.unhide_app(app_name)
        else:
            return self.hide_app(app_name)
    
    def get_pinned_apps(self) -> list:
        """Get list of pinned apps"""
        return self._preferences.get("pinned_apps", [])
    
    def is_app_pinned(self, app_name: str) -> bool:
        """Check if an app is pinned"""
        return app_name in self.get_pinned_apps()
    
    def pin_app(self, app_name: str) -> bool:
        """Pin an app"""
        pinned_apps = self.get_pinned_apps()
        if app_name not in pinned_apps:
            pinned_apps.append(app_name)
            self._preferences["pinned_apps"] = pinned_apps
            return self._save_preferences()
        return True  # Already pinned
    
    def unpin_app(self, app_name: str) -> bool:
        """Unpin an app"""
        pinned_apps = self.get_pinned_apps()
        if app_name in pinned_apps:
            pinned_apps.remove(app_name)
            self._preferences["pinned_apps"] = pinned_apps
            return self._save_preferences()
        return True  # Already unpinned
    
    def toggle_app_pinned(self, app_name: str) -> bool:
        """Toggle app pinned status"""
        if self.is_app_pinned(app_name):
            return self.unpin_app(app_name)
        else:
            return self.pin_app(app_name)
    
    def get_disabled_overlays(self) -> list:
        """Get list of disabled overlay names"""
        return self._preferences.get("disabled_overlays", [])
    
    def is_overlay_disabled(self, overlay_name: str) -> bool:
        """Check if an overlay is disabled"""
        disabled_overlays = self.get_disabled_overlays()
        return overlay_name in disabled_overlays
    
    def disable_overlay(self, overlay_name: str) -> bool:
        """Disable an overlay"""
        disabled_overlays = self.get_disabled_overlays()
        if overlay_name not in disabled_overlays:
            disabled_overlays.append(overlay_name)
            self._preferences["disabled_overlays"] = disabled_overlays
            return self._save_preferences()
        return True  # Already disabled
    
    def enable_overlay(self, overlay_name: str) -> bool:
        """Enable an overlay"""
        disabled_overlays = self.get_disabled_overlays()
        if overlay_name in disabled_overlays:
            disabled_overlays.remove(overlay_name)
            self._preferences["disabled_overlays"] = disabled_overlays
            return self._save_preferences()
        return True  # Already enabled
    
    def toggle_overlay_enabled(self, overlay_name: str) -> bool:
        """Toggle overlay enabled status"""
        if self.is_overlay_disabled(overlay_name):
            return self.enable_overlay(overlay_name)
        else:
            return self.disable_overlay(overlay_name)
    
    def get_tts_engine(self) -> str:
        """Get the current TTS engine preference"""
        return self._preferences.get("tts_engine", "piper")
    
    def set_tts_engine(self, engine: str) -> bool:
        """Set the TTS engine preference (piper, voicevox, or pyopenjtalk-plus)"""
        if engine not in ["piper", "voicevox", "openjtalk"]:
            print(f"[Preferences] Invalid TTS engine: {engine}")
            return False
        self._preferences["tts_engine"] = engine
        return self._save_preferences()

    def get_disabled_tts_engines(self) -> list:
        """Return a list of engine IDs that should be disabled even if installed"""
        return self._preferences.get("disabled_tts_engines", [])

    def set_disabled_tts_engines(self, engines: list) -> bool:
        """Persist the disabled TTS engine list"""
        safe_engines = list(dict.fromkeys(engines))
        self._preferences["disabled_tts_engines"] = safe_engines
        return self._save_preferences()
    
    def get_voicevox_speaker_id(self) -> int:
        """Get the VoiceVox speaker ID"""
        return self._preferences.get("voicevox_speaker_id", 2)
    
    def set_voicevox_speaker_id(self, speaker_id: int) -> bool:
        """Set the VoiceVox speaker ID"""
        self._preferences["voicevox_speaker_id"] = speaker_id
        return self._save_preferences()
    
    def get_piper_model(self) -> Optional[str]:
        """Get the Piper model path"""
        return self._preferences.get("piper_model")
    
    def set_piper_model(self, model_path: str) -> bool:
        """Set the Piper model path"""
        self._preferences["piper_model"] = model_path
        return self._save_preferences()
    
    def get_pyopenjtalk_voice(self) -> Optional[str]:
        """Get the PyOpenJTalk+ voice filename"""
        return self._preferences.get("pyopenjtalk_voice")
    
    def set_pyopenjtalk_voice(self, voice_filename: str) -> bool:
        """Set the PyOpenJTalk+ voice filename"""
        self._preferences["pyopenjtalk_voice"] = voice_filename
        return self._save_preferences()

    def get_keyboard_device_path(self) -> Optional[str]:
        """Return preferred keyboard device path if set"""
        return self._preferences.get("keyboard_device_path")

    def set_keyboard_device_path(self, device_path: Optional[str]) -> bool:
        """Set preferred keyboard device path (None clears override)"""
        self._preferences["keyboard_device_path"] = device_path
        return self._save_preferences()

    def get_auto_sleep_minutes(self, default: float = 5.0) -> float:
        """Return configured auto-sleep timeout in minutes (0 disables)."""
        return float(self._preferences.get("auto_sleep_minutes", default))

    def set_auto_sleep_minutes(self, minutes: float) -> bool:
        """Set inactivity timeout in minutes (values <=0 disable auto-sleep)."""
        safe_minutes = max(0.0, float(minutes))
        self._preferences["auto_sleep_minutes"] = safe_minutes
        return self._save_preferences()

# Global instance - will be initialized by main app
user_preferences = None

def initialize_preferences(config_dir: str):
    """Initialize the global preferences instance"""
    global user_preferences
    user_preferences = UserPreferences(config_dir)
    return user_preferences
