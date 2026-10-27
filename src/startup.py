"""
startup.py
----------
Launch Prinaka when the user logs in to Windows.

Adds or removes a value in the current user's Run registry key
(HKCU, no admin rights needed).
"""

import os
import sys

try:
    import winreg
    AVAILABLE = True
except ImportError:   # not on Windows
    AVAILABLE = False


APP_NAME = "Prinaka"
RUN_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> str:
    """Command line that starts Prinaka without a console window."""
    if getattr(sys, "frozen", False):          # packaged with PyInstaller
        return f'"{sys.executable}"'

    interpreter = sys.executable
    windowless  = os.path.join(os.path.dirname(interpreter), "pythonw.exe")
    if os.path.exists(windowless):
        interpreter = windowless

    main_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    return f'"{interpreter}" "{main_script}"'


def is_enabled(name: str = APP_NAME) -> bool:
    """Return True if Prinaka is registered to start with Windows."""
    if not AVAILABLE:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, name)
            return True
    except OSError:
        return False


def enable(name: str = APP_NAME) -> bool:
    """Register Prinaka to start with Windows. Returns True on success."""
    if not AVAILABLE:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, _command())
        return True
    except OSError:
        return False


def disable(name: str = APP_NAME) -> bool:
    """Remove the startup entry. Returns True if it is gone."""
    if not AVAILABLE:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def refresh(name: str = APP_NAME) -> None:
    """If enabled, rewrite the entry so it follows the project if it was moved."""
    if is_enabled(name):
        enable(name)
