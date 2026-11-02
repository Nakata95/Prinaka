"""
poller.py
---------
Runs a slow reading function in a background thread, on a fixed interval,
and delivers each result to the GUI thread through a Qt signal.
"""

import threading
import time
from typing import Callable

from PyQt5.QtCore import QObject, pyqtSignal


class BackgroundPoller(QObject):
    """
    Calls `read(cycle)` every `interval_s` seconds in a background thread.

    Emits `updated(dict)` with whatever `read` returns. start() and stop()
    can be called repeatedly (for instance on show/hide); stopping makes the
    running thread exit within a tenth of a second.

    Args:
        read: Function taking the cycle number (0, 1, 2...) and returning a dict.
        interval_s: Seconds between two readings.
        parent: Optional Qt parent.
        com: Initialise COM in the thread (needed by WMI). Leave it off for
            readers using WinRT streams, which then wait forever.
    """

    updated = pyqtSignal(dict)

    def __init__(self, read: Callable[[int], dict], interval_s: float, parent=None, com: bool = True):
        super().__init__(parent)
        self._read       = read
        self._interval_s = interval_s
        self._com        = com
        self._generation = 0

    def start(self) -> None:
        self._generation += 1
        threading.Thread(target=self._run, args=(self._generation,), daemon=True).start()

    def stop(self) -> None:
        self._generation += 1   # makes the running thread exit

    def _run(self, generation: int) -> None:
        pythoncom = None
        if self._com:
            try:
                import pythoncom   # WMI (temperature) needs COM initialised in every thread
                pythoncom.CoInitialize()
            except ImportError:
                pythoncom = None

        try:
            self._loop(generation)
        finally:
            if pythoncom:
                pythoncom.CoUninitialize()

    def _loop(self, generation: int) -> None:
        cycle = 0
        while generation == self._generation:
            data = self._read(cycle)
            if generation != self._generation:
                return
            self.updated.emit(data)
            cycle += 1

            for _ in range(int(self._interval_s * 10)):   # interruptible sleep
                if generation != self._generation:
                    return
                time.sleep(0.1)
