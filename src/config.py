"""
config.py
---------
Application settings manager for Prinaka.

Uses QSettings to store user preferences in the Windows registry.
Settings are saved automatically on each change and persist between sessions.

Registry path: HKEY_CURRENT_USER/Software/NakaCorp/Prinaka

Stored settings:
- skin               : active skin name (str)
- size_percent       : Prinny's size, 75 to 200 (int)
- volume             : sound volume 0-100 (int)
- muted              : mute state (bool)
- language           : active language code (str)
- media_enabled      : whether to display current media (bool)
- media_spotify_only : follow only Spotify, not every media app (bool)
- player_window_pos  : last position of the mini player, "x,y" (str)
- ram_alert_enabled  : whether to show RAM alert notifications (bool)
- ram_alert_threshold: RAM percentage threshold for alerts (int)
- cpu/disk/temp/battery_alert_enabled and _threshold: same for the other
  alerts (see alerts.py)
- quotes_enabled      : random quote bubbles (bool)
- quotes_frequency    : 'low', 'normal' or 'high' (str)
- reactions_enabled   : contextual reactions, see reactions.py (bool)
- defender_enabled    : relay Windows Defender detections (bool)
- dnd_fullscreen      : hide Prinny and stay silent during full-screen apps (bool)
- info_window_pos     : last position of the system info window, "x,y" (str)
- net_window_pos      : last position of the network overlay, "x,y" (str)
- presence_autostart  : re-apply the last Discord presence at launch (bool)
- presence_last_profile: name of the last active presence profile (str)
- presence_preview_visible: show the preview panel in the presence window (bool)
"""

from PyQt5.QtCore import QSettings


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS = {
    "skin":                "default",
    "size_percent":        100,
    "volume":              50,
    "muted":               False,
    "language":            "en",
    "media_enabled":       True,
    "media_spotify_only":  True,
    "player_window_pos":   "",
    "ram_alert_enabled":   True,
    "ram_alert_threshold": 80,
    "cpu_alert_enabled":     False,
    "cpu_alert_threshold":   90,
    "disk_alert_enabled":    True,
    "disk_alert_threshold":  90,
    "temp_alert_enabled":    False,
    "temp_alert_threshold":  85,
    "battery_alert_enabled": True,
    "battery_alert_threshold": 20,
    "quotes_enabled":      True,
    "quotes_frequency":    "normal",
    "reactions_enabled":   True,
    "dnd_fullscreen":      True,
    "defender_enabled":    True,
    "info_window_pos":     "",
    "net_window_pos":      "",
    "presence_autostart":  False,
    "presence_last_profile": "",
    "presence_preview_visible": True,
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