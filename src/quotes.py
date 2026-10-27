"""
quotes.py
---------
Localized quote lists for Prinaka's speech bubbles.

Quotes live in assets/quotes.json, grouped by language then by category:

    {"fr": {"random": [...], "late_night": [...]}, "en": {...}}

A category falls back to English when the active language does not define it.
Texts may contain format placeholders such as {count}.
"""

import json
import os
import random

from utils import resource_path, get_current_language


_data: dict | None = None
_last: dict = {}   # category -> last quote shown, to avoid immediate repeats


def _load() -> dict:
    global _data
    if _data is None:
        try:
            with open(resource_path(os.path.join("assets", "quotes.json")), "r", encoding="utf-8") as f:
                _data = json.load(f)
        except Exception as e:
            print(f"[quotes] Failed to load quotes: {e}")
            _data = {}
    return _data


def format_number(n: int) -> str:
    """Format `n` with thousands separators matching the active language."""
    sep = " " if get_current_language() == "fr" else ","
    return f"{n:,}".replace(",", sep)


def get_quote(category: str, **fmt) -> str | None:
    """
    Pick a random quote of `category` in the active language.

    Args:
        category: Category name (e.g. 'random', 'late_night').
        **fmt: Values for the placeholders of the quote.

    Returns:
        The formatted quote, or None if the category has no quote.
    """
    data = _load()
    pool = data.get(get_current_language(), {}).get(category) or data.get("en", {}).get(category)
    if not pool:
        return None

    choices = [q for q in pool if q != _last.get(category)] or pool
    quote = random.choice(choices)
    _last[category] = quote

    try:
        return quote.format(**fmt)
    except (KeyError, IndexError):
        return quote
