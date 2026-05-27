"""
utils.py
--------
Utility functions used across the entire Prinaka project.

Covers:
- PyInstaller path resolution
- Sprite loading
- Multi-monitor screen rect
- Localisation (language support)
"""

import os
import sys
import json
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES = ["en", "fr"]
DEFAULT_LANGUAGE = "en"

# Internal cache for the loaded locale strings
_locale: dict = {}
_current_language: str = DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# PyInstaller compatibility
# ---------------------------------------------------------------------------

def resource_path(relative_path: str) -> str:
    """
    Return the absolute path to a resource file.

    Works both in development (normal Python) and when packaged
    with PyInstaller, where files are extracted to a temp folder.

    In development, resolves paths relative to the project root
    (one level above src/).

    Args:
        relative_path: Path relative to the project root.

    Returns:
        Absolute path as a string.
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)

    # Remonte d'un niveau au-dessus de src/ pour trouver la racine du projet
    src_dir      = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(src_dir)
    return os.path.join(project_root, relative_path)


# ---------------------------------------------------------------------------
# Sprite loading
# ---------------------------------------------------------------------------

def load_sprites(folder: str) -> list:
    """
    Load all PNG frames from a folder and return them as a list of QPixmap.

    Frames are sorted numerically by filename (1.png, 2.png, ...).
    Returns an empty list if the folder does not exist.

    Args:
        folder: Path to the animation folder (e.g. 'assets/sprites/default/idle').

    Returns:
        List of QPixmap objects, one per frame.
    """
    frames = []
    folder = resource_path(folder)

    if not os.path.exists(folder):
        return frames

    files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".png")],
        key=lambda x: int(os.path.splitext(x)[0])
    )

    for f in files:
        frames.append(QPixmap(os.path.join(folder, f)))

    return frames


# ---------------------------------------------------------------------------
# Multi-monitor support
# ---------------------------------------------------------------------------

def get_total_screen_rect():
    """
    Return a QRect covering all connected monitors combined.

    Prinny uses this to roam freely across multiple screens.

    Returns:
        QRect representing the total desktop area.
    """
    desktop = QApplication.desktop()
    total_rect = desktop.screenGeometry(0)
    for i in range(1, desktop.screenCount()):
        total_rect = total_rect.united(desktop.screenGeometry(i))
    return total_rect


# ---------------------------------------------------------------------------
# Localisation
# ---------------------------------------------------------------------------

def load_language(lang: str) -> None:
    """
    Load a language file into the internal locale cache.

    Falls back to English if the requested language file is not found.

    Args:
        lang: Language code ('en' or 'fr').
    """
    global _locale, _current_language

    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE

    path = resource_path(os.path.join("assets", "locales", f"{lang}.json"))

    if not os.path.exists(path):
        path = resource_path(os.path.join("assets", "locales", "en.json"))
        lang = DEFAULT_LANGUAGE

    try:
        with open(path, "r", encoding="utf-8") as f:
            _locale = json.load(f)
        _current_language = lang
    except Exception as e:
        print(f"[utils] Failed to load language '{lang}': {e}")
        _locale = {}


def t(key: str) -> str:
    """
    Translate a key into the currently loaded language.

    If the key is not found, returns the key itself so nothing
    breaks visually even if a translation is missing.

    Args:
        key: Translation key (e.g. 'menu_quit').

    Returns:
        Translated string, or the key as fallback.
    """
    return _locale.get(key, key)


def get_current_language() -> str:
    """
    Return the currently active language code.

    Returns:
        Language code string (e.g. 'en' or 'fr').
    """
    return _current_language