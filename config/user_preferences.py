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
            "created_at": "2025-07-14",
            "version": "1.0"
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

# Global instance - will be initialized by main app
user_preferences = None

def initialize_preferences(config_dir: str):
    """Initialize the global preferences instance"""
    global user_preferences
    user_preferences = UserPreferences(config_dir)
    return user_preferences
