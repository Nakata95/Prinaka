"""
reactions.py
------------
Contextual reactions for Prinaka.

ReactionEngine decides *when* Prinny should comment on something (greeting,
late night, click/keystroke milestones, battery plugged/unplugged). It only
returns a quote category and its format values; the caller picks the text
(see quotes.py) and displays it. All inputs are passed in, so it can be
tested without a running app.
"""

from datetime import datetime, timedelta
from typing import Optional

from quotes import format_number


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLICK_MILESTONES = (500, 1000, 5000, 10000, 25000, 50000, 100000)
KEY_MILESTONES   = (1000, 5000, 10000, 25000, 50000, 100000)

LATE_NIGHT_HOURS = range(1, 5)             # 01:00 -> 04:59
LATE_NIGHT_GAP   = timedelta(minutes=90)   # between two late-night reminders
MIN_GAP          = timedelta(minutes=2)    # between two non-greeting reactions


def greeting_category(hour: int) -> str:
    """Return the greeting quote category for an hour of the day."""
    if 5 <= hour < 12:
        return "greeting_morning"
    if 12 <= hour < 18:
        return "greeting_day"
    if 18 <= hour < 23:
        return "greeting_evening"
    return "greeting_night"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ReactionEngine:
    """Stateful rules deciding which reaction (if any) to trigger."""

    def __init__(self):
        self._greeted        = False
        self._last_reaction: Optional[datetime] = None
        self._last_late:     Optional[datetime] = None
        self._clicks_done    = 0
        self._keys_done      = 0
        self._was_plugged:   Optional[bool] = None

    def check(self, now: datetime, clicks: int, keys: int,
              battery: Optional[tuple]) -> Optional[tuple[str, dict]]:
        """
        Evaluate the rules once.

        Args:
            now: Current local time.
            clicks: Mouse clicks since the app started.
            keys: Keystrokes since the app started.
            battery: (percent, plugged) or None when there is no battery.

        Returns:
            (quote_category, format_values) or None if nothing to say.
        """
        if not self._greeted:
            self._greeted = True
            self._last_reaction = now
            self._seed(clicks, keys, battery)
            return greeting_category(now.hour), {}

        if self._last_reaction and now - self._last_reaction < MIN_GAP:
            return None

        reaction = (
            self._battery_reaction(battery)
            or self._milestone_reaction(clicks, keys)
            or self._late_night_reaction(now)
        )
        if reaction:
            self._last_reaction = now
        return reaction

    # -----------------------------------------------------------------------
    # Rules
    # -----------------------------------------------------------------------

    def _seed(self, clicks: int, keys: int, battery: Optional[tuple]) -> None:
        """Take the initial state as the baseline so it is not announced."""
        self._clicks_done = max((m for m in CLICK_MILESTONES if m <= clicks), default=0)
        self._keys_done   = max((m for m in KEY_MILESTONES if m <= keys), default=0)
        self._was_plugged = battery[1] if battery else None

    def _battery_reaction(self, battery: Optional[tuple]):
        if battery is None:
            return None
        plugged = battery[1]
        previous, self._was_plugged = self._was_plugged, plugged
        if previous is None or previous == plugged:
            return None
        return ("battery_plugged" if plugged else "battery_unplugged"), {}

    def _milestone_reaction(self, clicks: int, keys: int):
        for value, done_attr, milestones, category in (
            (clicks, "_clicks_done", CLICK_MILESTONES, "milestone_clicks"),
            (keys,   "_keys_done",   KEY_MILESTONES,   "milestone_keys"),
        ):
            reached = max((m for m in milestones if m <= value), default=0)
            if reached > getattr(self, done_attr):
                setattr(self, done_attr, reached)
                return category, {"count": format_number(reached)}
        return None

    def _late_night_reaction(self, now: datetime):
        if now.hour not in LATE_NIGHT_HOURS:
            return None
        if self._last_late and now - self._last_late < LATE_NIGHT_GAP:
            return None
        self._last_late = now
        return "late_night", {}
