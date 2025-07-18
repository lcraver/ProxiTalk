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

# Global instance - will be initialized by main app
user_preferences = None

def initialize_preferences(config_dir: str):
    """Initialize the global preferences instance"""
    global user_preferences
    user_preferences = UserPreferences(config_dir)
    return user_preferences
