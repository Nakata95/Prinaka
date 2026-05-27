"""
media.py
--------
Current media playback detection for Prinaka.

Uses the Windows Media Transport Controls API (via winsdk) to retrieve
the currently playing track from any application (Spotify, YouTube,
Windows Media Player, etc.).

This module is Windows-only.
"""

import asyncio


# ---------------------------------------------------------------------------
# Media info
# ---------------------------------------------------------------------------

def get_current_media_info() -> str | None:
    """
    Retrieve the title and artist of the currently playing media.

    Works with any application that exposes media info to Windows
    (Spotify, browsers, Windows Media Player, etc.).

    Returns:
        Formatted string 'Title\\n(by Artist)' if media is playing,
        or None if nothing is playing or an error occurs.
    """
    async def _fetch() -> tuple[str, str]:
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager
        )
        sessions = await MediaManager.request_async()
        current  = sessions.get_current_session()

        if not current:
            return None, None

        info   = await current.try_get_media_properties_async()
        artist = getattr(info, "artist", "") or ""
        title  = getattr(info, "title",  "") or ""
        return artist, title

    try:
        artist, title = asyncio.run(_fetch())
        if title:
            if artist:
                return f"{title}\n(by {artist})"
            return title
    except Exception as e:
        print(f"[media] Failed to get media info: {e}")

    return None


def is_media_playing() -> bool:
    """
    Check whether any media is currently playing.

    Returns:
        True if a track is detected, False otherwise.
    """
    return get_current_media_info() is not None