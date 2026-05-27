"""
listeners.py
------------
Global mouse and keyboard listeners using pynput.

Tracks:
- Total mouse clicks since the app started
- Total keystrokes since the app started

These counters are displayed in the system info window.
The listeners run in background threads automatically.
"""

from pynput import mouse, keyboard


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

click_count: int = 0
key_count: int = 0


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def _on_click(x, y, button, pressed) -> None:
    """
    Increment the click counter on each mouse button press.

    Args:
        x: Mouse X position.
        y: Mouse Y position.
        button: Which button was pressed.
        pressed: True if pressed, False if released.
    """
    global click_count
    if pressed:
        click_count += 1


def _on_press(key) -> None:
    """
    Increment the keystroke counter on each key press.

    Args:
        key: The key that was pressed.
    """
    global key_count
    key_count += 1


# ---------------------------------------------------------------------------
# Listeners (started once at import time)
# ---------------------------------------------------------------------------

_mouse_listener = mouse.Listener(on_click=_on_click)
_keyboard_listener = keyboard.Listener(on_press=_on_press)

_mouse_listener.start()
_keyboard_listener.start()


# ---------------------------------------------------------------------------
# Public accessors
# ---------------------------------------------------------------------------

def get_click_count() -> int:
    """
    Return the total number of mouse clicks since the app started.

    Returns:
        Integer click count.
    """
    return click_count


def get_key_count() -> int:
    """
    Return the total number of keystrokes since the app started.

    Returns:
        Integer keystroke count.
    """
    return key_count


def reset_counts() -> None:
    """
    Reset both counters to zero.
    """
    global click_count, key_count
    click_count = 0
    key_count = 0