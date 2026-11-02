"""
media.py
--------
Current media playback detection and control for Prinaka.

Uses the Windows Media Transport Controls API (via winsdk). It can follow any
application that exposes its playback to Windows (browsers, Windows Media
Player...) or only Spotify, and send play/pause, previous, next and seek
commands to it.

This module is Windows-only.
"""

import asyncio
import threading
from datetime import datetime, timezone

SOURCE_SPOTIFY = "spotify"
SOURCE_ANY     = "any"

THUMBNAIL_TIMEOUT_S = 3

REPEAT_NONE, REPEAT_TRACK, REPEAT_LIST = 0, 1, 2   # MediaPlaybackAutoRepeatMode

PLAYING = 4   # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING

_thumbnail_cache: dict = {}   # track key -> image bytes (or None), last track only


# ---------------------------------------------------------------------------
# Session lookup
# ---------------------------------------------------------------------------

def is_spotify(app_id: str) -> bool:
    """True for the Spotify desktop app ('Spotify.exe') and its Store version."""
    return "spotify" in (app_id or "").lower()


def is_spotify_running() -> bool:
    """True if a Spotify process exists (it only shows up in Windows' media controls once a track has played)."""
    try:
        import psutil
        return any((p.info["name"] or "").lower() == "spotify.exe" for p in psutil.process_iter(["name"]))
    except Exception:
        return False


def pick_session(manager, source: str):
    """
    Choose the session to follow.

    Args:
        manager: A GlobalSystemMediaTransportControlsSessionManager.
        source: SOURCE_SPOTIFY (only Spotify) or SOURCE_ANY (Windows' current session).

    Returns:
        The session, or None if there is none.
    """
    if source == SOURCE_SPOTIFY:
        for session in manager.get_sessions():
            if is_spotify(session.source_app_user_model_id):
                return session
        return None
    return manager.get_current_session()


async def _get_manager():
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager
    )
    return await MediaManager.request_async()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

async def _read_thumbnail(info) -> bytes | None:
    try:
        from winsdk.windows.storage.streams import DataReader
        async def load():
            stream = await info.thumbnail.open_read_async()
            reader = DataReader(stream)
            await reader.load_async(stream.size)
            return stream.size, reader
        size, reader = await asyncio.wait_for(load(), THUMBNAIL_TIMEOUT_S)   # never block the player on a cover
        data = bytearray(size)
        reader.read_bytes(data)
        return bytes(data)
    except Exception:
        return None


def _seconds(delta) -> float:
    return delta.total_seconds() if delta else 0.0


async def _fetch_state(source: str, with_thumbnail: bool) -> dict | None:
    manager = await _get_manager()
    session = pick_session(manager, source)
    if not session:
        return None

    info = await session.try_get_media_properties_async()
    title, artist = info.title or "", info.artist or ""
    if not title:
        return None

    playback = session.get_playback_info()
    playing  = playback.playback_status == PLAYING
    timeline = session.get_timeline_properties()
    duration = _seconds(timeline.end_time) - _seconds(timeline.start_time)
    position = _seconds(timeline.position) - _seconds(timeline.start_time)

    # The player only reports its position now and then: add the time since
    if playing and timeline.last_updated_time:
        position += (datetime.now(timezone.utc) - timeline.last_updated_time).total_seconds()
    position = max(0.0, min(position, duration)) if duration > 0 else 0.0

    key = f"{session.source_app_user_model_id}|{artist}|{title}"
    thumbnail = None
    if with_thumbnail:
        if key not in _thumbnail_cache:
            _thumbnail_cache.clear()
            _thumbnail_cache[key] = await _read_thumbnail(info)
        thumbnail = _thumbnail_cache[key]

    return {
        "key": key, "title": title, "artist": artist, "playing": playing,
        "position": position, "duration": duration, "thumbnail": thumbnail,
        "shuffle": bool(playback.is_shuffle_active),
        "repeat": int(playback.auto_repeat_mode or REPEAT_NONE),
    }


def get_media_state(source: str = SOURCE_ANY, with_thumbnail: bool = False) -> dict | None:
    """
    Snapshot of the followed session.

    Returns:
        A dict with key, title, artist, playing, position and duration (seconds)
        and thumbnail (image bytes or None), or None if nothing is available.
    """
    try:
        return asyncio.run(_fetch_state(source, with_thumbnail))
    except Exception as e:
        print(f"[media] Failed to get media info: {e}")
        return None


def get_current_media_info(source: str = SOURCE_ANY) -> str | None:
    """
    Title and artist of the current media, formatted for a speech bubble.

    Returns:
        'Title\\n(by Artist)', or the title alone, or None if nothing is playing.
    """
    state = get_media_state(source)
    if not state:
        return None
    if state["artist"]:
        return f"{state['title']}\n(by {state['artist']})"
    return state["title"]


def is_media_playing() -> bool:
    """Check whether any media is currently detected."""
    return get_current_media_info() is not None


# ---------------------------------------------------------------------------
# Control
# ---------------------------------------------------------------------------

COMMANDS = ("toggle", "next", "previous")


async def _send(source: str, command: str, value: float) -> None:
    manager = await _get_manager()
    session = pick_session(manager, source)
    if not session:
        return
    if command == "toggle":
        await session.try_toggle_play_pause_async()
    elif command == "next":
        await session.try_skip_next_async()
    elif command == "previous":
        await session.try_skip_previous_async()
    elif command == "shuffle":
        await session.try_change_shuffle_active_async(bool(value))
    elif command == "repeat":
        await session.try_change_auto_repeat_mode_async(int(value))
    elif command == "seek":
        await session.try_change_playback_position_async(int(value * 10_000_000))   # 100 ns ticks


def send_command(source: str, command: str, value: float = 0.0) -> None:
    """
    Send 'toggle', 'next', 'previous', 'seek' (value = seconds), 'shuffle'
    (value = on/off) or 'repeat' (value = a REPEAT_* mode) to the followed session, without blocking the caller.
    """
    def run():
        try:
            asyncio.run(_send(source, command, value))
        except Exception as e:
            print(f"[media] Command '{command}' failed: {e}")

    threading.Thread(target=run, daemon=True).start()
