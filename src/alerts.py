"""
alerts.py
---------
System alerts for Prinaka (RAM, CPU, disk, temperature, battery).

Each alert is described by an AlertRule. AlertMonitor reads the enabled
rules and reports which ones are active and which just triggered, so the
UI layer only has to display them.

Config keys per rule (see config.py):
    <key>_alert_enabled    : bool
    <key>_alert_threshold  : int
"""

import os
from dataclasses import dataclass
from typing import Callable, Optional

import psutil

from system_stats import (
    get_cpu_usage, get_cpu_temperature_c, get_ram_usage, get_disk_usage,
)


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def _read_ram() -> Optional[float]:
    return get_ram_usage()["percent"]


def _read_cpu() -> Optional[float]:
    return get_cpu_usage()


def _read_disk() -> Optional[float]:
    """Used percentage of the system drive."""
    drive = os.environ.get("SystemDrive", "C:") + "\\"
    return 100 - get_disk_usage(drive)["free_percent"]


def _read_temp() -> Optional[float]:
    """CPU temperature in °C, or None when it cannot be read."""
    return get_cpu_temperature_c()


def _read_battery() -> Optional[float]:
    """Battery percentage, or None on desktops and while plugged in."""
    battery = psutil.sensors_battery()
    if battery is None or battery.power_plugged:
        return None
    return battery.percent


def _has_battery() -> bool:
    return psutil.sensors_battery() is not None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AlertRule:
    """
    Description of one alert.

    Attributes:
        key: Short id, also the prefix of the config keys.
        icon: Emoji shown in the menu.
        name_key: Locale key of the display name.
        message_key: Locale key of the bubble text ({value} is the reading).
        unit: Unit appended to values ('%' or '°C').
        above: True to alert when value >= threshold, False when <=.
        presets: Thresholds offered in the menu.
        sustain: Consecutive readings needed before triggering (avoids spikes).
        hysteresis: Margin past the threshold before the alert clears.
        reader: Returns the current value, or None when unavailable.
        available: Whether this alert makes sense on this machine.
    """
    key:        str
    icon:       str
    name_key:   str
    message_key: str
    unit:       str
    above:      bool
    presets:    tuple
    sustain:    int
    hysteresis: int
    reader:     Callable[[], Optional[float]]
    available:  Callable[[], bool] = lambda: True

    @property
    def enabled_key(self) -> str:
        return f"{self.key}_alert_enabled"

    @property
    def threshold_key(self) -> str:
        return f"{self.key}_alert_threshold"

    @property
    def symbol(self) -> str:
        return "≥" if self.above else "≤"


RULES = (
    AlertRule("ram",     "⚠️", "menu_alert_ram",     "alert_ram",     "%",  True,
              (70, 80, 90, 95), 1, 2, _read_ram),
    AlertRule("cpu",     "🔥", "menu_alert_cpu",     "alert_cpu",     "%",  True,
              (80, 90, 95),     3, 5, _read_cpu),
    AlertRule("disk",    "💾", "menu_alert_disk",    "alert_disk",    "%",  True,
              (80, 90, 95),     1, 1, _read_disk),
    AlertRule("temp",    "🌡", "menu_alert_temp",    "alert_temp",    "°C", True,
              (75, 85, 90),     2, 3, _read_temp),
    AlertRule("battery", "🔋", "menu_alert_battery", "alert_battery", "%",  False,
              (10, 15, 20, 30), 1, 2, _read_battery, _has_battery),
)


def get_rule(key: str) -> AlertRule:
    """Return the rule called `key`."""
    return next(r for r in RULES if r.key == key)


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class AlertMonitor:
    """
    Evaluates the enabled alert rules and tracks which ones are active.

    Args:
        config: ConfigManager used to read enabled flags and thresholds.
    """

    def __init__(self, config):
        self._config = config
        self._streak: dict = {}
        self._active: dict = {}

        # key -> last reading (None = unavailable); missing = never read
        self.last_values: dict = {}

    def clear(self, key: str) -> None:
        """Forget the state of one rule (e.g. after it was disabled)."""
        self._streak.pop(key, None)
        self._active.pop(key, None)

    def check(self) -> tuple[list, list]:
        """
        Read every enabled rule once.

        Returns:
            (active, new): `active` is a list of (rule, value) for all alerts
            currently on, `new` the rules that just triggered on this check.
        """
        active, new = [], []

        for rule in RULES:
            if not self._config.get(rule.enabled_key) or not rule.available():
                self.clear(rule.key)
                continue

            try:
                value = rule.reader()
            except Exception:
                value = None
            self.last_values[rule.key] = value

            if value is None:
                self.clear(rule.key)
                continue

            threshold = self._config.get(rule.threshold_key)

            if rule.key in self._active:
                margin = -rule.hysteresis if rule.above else rule.hysteresis
                if (value >= threshold + margin) if rule.above else (value <= threshold + margin):
                    self._active[rule.key] = value
                    active.append((rule, value))
                else:
                    self.clear(rule.key)
                continue

            hit = value >= threshold if rule.above else value <= threshold
            streak = self._streak.get(rule.key, 0) + 1 if hit else 0
            self._streak[rule.key] = streak

            if streak >= rule.sustain:
                self._streak[rule.key] = 0
                self._active[rule.key] = value
                active.append((rule, value))
                new.append(rule)

        return active, new
