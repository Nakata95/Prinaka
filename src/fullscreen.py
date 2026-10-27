"""
fullscreen.py
-------------
Detects when Windows considers the user busy: a game or video in
full screen, or a presentation.

Uses SHQueryUserNotificationState, the same API apps use to decide
whether they may show notifications.
"""

import ctypes
import sys


# SHQueryUserNotificationState values that mean "do not disturb"
_QUNS_BUSY                    = 2   # full-screen app (or presentation settings)
_QUNS_RUNNING_D3D_FULL_SCREEN = 3   # exclusive full-screen game
_QUNS_PRESENTATION_MODE       = 4
_QUNS_APP                     = 7   # full-screen Store app

_BUSY_STATES = {
    _QUNS_BUSY,
    _QUNS_RUNNING_D3D_FULL_SCREEN,
    _QUNS_PRESENTATION_MODE,
    _QUNS_APP,
}


def is_fullscreen_busy() -> bool:
    """
    Return True if a full-screen app or presentation is running.

    Always False on other platforms or if the query fails.
    """
    if sys.platform != "win32":
        return False
    try:
        state = ctypes.c_int()
        result = ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
        return result == 0 and state.value in _BUSY_STATES
    except Exception:
        return False
