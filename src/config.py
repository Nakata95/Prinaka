"""
config.py
---------
Application settings manager for Prinaka.

Uses QSettings to store user preferences in the Windows registry.
Settings are saved automatically on each change and persist between sessions.

Registry path: HKEY_CURRENT_USER/Software/NakaCorp/Prinaka

Stored settings:
- skin         : active skin name (str)
- volume       : sound volume 0-100 (int)
- muted        : mute state (bool)
- language     : active language code (str)
- media_enabled: whether to display current media (bool)
"""

from PyQt5.QtCore import QSettings


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS = {
    "skin":          "default",
    "volume":        50,
    "muted":         False,
    "language":      "en",
    "media_enabled": True,
}


# ---------------------------------------------------------------------------
# Config manager
# ---------------------------------------------------------------------------

class ConfigManager:
    """
    Wrapper around QSettings for easy typed access to app preferences.

    Usage:
        config = ConfigManager()
        config.get("volume")        # returns 50
        config.set("volume", 80)    # saves immediately
    """

    def __init__(self):
        self._settings = QSettings(
            QSettings.IniFormat,
            QSettings.UserScope,
            "NakaCorp",
            "Prinaka"
        )

    def get(self, key: str):
        """
        Return the value for a setting key.

        Uses the default value defined in DEFAULTS if the key
        has never been set. Handles type casting automatically
        (bools and ints are returned with the correct type).

        Args:
            key: Setting key name (e.g. 'volume').

        Returns:
            The stored value, or the default if not set.
        """
        default = DEFAULTS.get(key)

        if isinstance(default, bool):
            return self._settings.value(key, default, type=bool)
        elif isinstance(default, int):
            return self._settings.value(key, default, type=int)
        else:
            return self._settings.value(key, default)

    def set(self, key: str, value) -> None:
        """
        Save a setting value immediately.

        Args:
            key: Setting key name (e.g. 'volume').
            value: Value to store.
        """
        self._settings.setValue(key, value)

    def reset(self) -> None:
        """
        Reset all settings to their default values.
        """
        for key, value in DEFAULTS.items():
            self._settings.setValue(key, value)

    def file_path(self) -> str:
        """
        Return the path to the settings file (useful for debugging).

        Returns:
            Absolute path to the QSettings file.
        """
        return self._settings.fileName()