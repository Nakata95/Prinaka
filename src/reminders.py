"""
reminders.py
------------
Timers and reminders ("remind me in 25 minutes", "remind me at 22:30").

They live in memory only: nothing is written to the disk, so they are gone when
Prinaka quits. Each one is a single-shot QTimer, so this class must be used from
the GUI thread.
"""

import itertools
import re
import time
from datetime import datetime, timedelta

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_SECONDS  = 10
MAX_SECONDS  = 24 * 3600
MAX_ACTIVE   = 20
MAX_LABEL    = 80
_CLOCK       = re.compile(r"^(\d{1,2})\s*[:h]\s*(\d{2})?$")


class ReminderError(ValueError):
    """The delay or the time asked for is not usable."""


def seconds_until(minutes=None, at: str = "", now: datetime | None = None) -> float:
    """
    Seconds from now for 'in N minutes' or 'at HH:MM' (the next time it is that hour).

    Raises:
        ReminderError: nothing given, a bad time, or a delay outside 10 s .. 24 h.
    """
    now = now or datetime.now()
    if at:
        match = _CLOCK.match(at.strip().lower())
        if not match:
            raise ReminderError("at must look like 22:30")
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ReminderError("at must be a time between 00:00 and 23:59")
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        seconds = (target - now).total_seconds()
    elif minutes is not None:
        try:
            seconds = float(minutes) * 60
        except (TypeError, ValueError):
            raise ReminderError("minutes must be a number") from None
    else:
        raise ReminderError("give a delay in minutes or a time")
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        raise ReminderError("the delay must be between 10 seconds and 24 hours")
    return seconds


class Reminders(QObject):
    """Active reminders; `due(label)` is emitted when one rings."""

    due = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ids = itertools.count(1)
        self._active = {}                      # id -> (label, due epoch seconds, QTimer)

    def add(self, seconds: float, label: str) -> int:
        """
        Raises:
            ReminderError: too many reminders already.
        """
        if len(self._active) >= MAX_ACTIVE:
            raise ReminderError(f"already {MAX_ACTIVE} reminders, cancel some first")
        ident = next(self._ids)
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda i=ident: self._ring(i))
        label = " ".join((label or "").split())[:MAX_LABEL]
        self._active[ident] = (label, time.time() + seconds, timer)
        timer.start(int(seconds * 1000))
        return ident

    def _ring(self, ident: int) -> None:
        entry = self._active.pop(ident, None)
        if entry:
            self.due.emit(entry[0])

    def active(self) -> list:
        """[(label, seconds left)] soonest first."""
        now = time.time()
        return sorted(((label, max(0, int(due - now))) for label, due, _ in self._active.values()), key=lambda x: x[1])

    def cancel(self, label: str = "") -> int:
        """Cancel the reminders whose label contains `label` (all of them if empty). Returns how many."""
        label = (label or "").strip().lower()
        gone = [i for i, (text, _, _) in self._active.items() if not label or label in text.lower()]
        for ident in gone:
            self._active.pop(ident)[2].stop()
        return len(gone)
