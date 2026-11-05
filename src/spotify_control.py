"""
spotify_control.py
------------------
Starts Spotify and plays something asked for (see ai_tools.py).

Spotify is started through its own Windows address type ('spotify:'), the same
way a link in a browser does, so no program path is ever built here. The title
asked for is looked up on the web (open.spotify.com links); when it is found,
Spotify is sent 'spotify:track:<id>', otherwise it is sent a search and the
user presses play. Everything that goes into a spotify: address is checked
first: an id is 22 letters and digits, the search words are percent-encoded.

Pausing, skipping and the rest stay with media.py.
"""

import concurrent.futures
import os
import re
import time
import urllib.parse

import media
import websearch


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

START_WAIT_S   = 15      # how long Spotify gets to appear after being started
PLAY_WAIT_S    = 5       # how long to wait to see whether the track started
POLL_S         = 0.5
MAX_QUERY      = 120
KINDS          = ("track", "album", "playlist", "artist")

HOST  = "open.spotify.com"
_PATH = re.compile(r"^/(?:intl-[a-z]{2}/)?(track|album|playlist|artist)/([A-Za-z0-9]{22})$")


class SpotifyError(Exception):
    """Spotify could not be started or reached."""


# ---------------------------------------------------------------------------
# Starting
# ---------------------------------------------------------------------------

def _open_uri(uri: str) -> None:
    """Hand a spotify: address to Windows, which gives it to the Spotify app."""
    if not uri.startswith("spotify:"):
        raise SpotifyError("not a Spotify address")
    try:
        os.startfile(uri)
    except OSError as e:
        raise SpotifyError("Spotify does not seem to be installed") from e


def launch() -> str:
    """
    Start Spotify and wait until it runs.

    Returns:
        'already running' or 'started'.

    Raises:
        SpotifyError: not installed, or it did not appear in time.
    """
    if media.is_spotify_running():
        return "already running"
    _open_uri("spotify:")
    deadline = time.monotonic() + START_WAIT_S
    while time.monotonic() < deadline:
        if media.is_spotify_running():
            time.sleep(2)          # let its window and its player come up
            return "started"
        time.sleep(POLL_S)
    raise SpotifyError("Spotify did not start in time")


# ---------------------------------------------------------------------------
# Playing
# ---------------------------------------------------------------------------

def find_item(query: str, language: str = "en", kind: str = ""):
    """
    Look for the Spotify link of what was asked.

    Args:
        kind: 'track', 'album', 'playlist' or 'artist' to only accept that kind
            (empty: the first of any kind).

    Returns:
        (kind, id) of the first matching open.spotify.com result, or None.
    """
    scope = f"site:open.spotify.com/{kind}" if kind in KINDS else "site:open.spotify.com"
    try:
        results = websearch.search(f"{scope} {query}", language)
    except websearch.SearchError:
        return None
    for result in results:
        parts = urllib.parse.urlsplit(result.get("url", ""))
        match = _PATH.match(parts.path) if parts.hostname == HOST else None
        if match and (not kind or match.group(1) == kind):
            return match.group(1), match.group(2)
    return None


def _now_playing() -> str:
    state = media.get_media_state(media.SOURCE_SPOTIFY)
    if state and state["playing"]:
        return f"{state['title']} by {state['artist'] or 'unknown'}"
    return ""


def play(query: str, language: str = "en", kind: str = "") -> str:
    """
    Start Spotify if needed and play what was asked.

    Args:
        query: Title and artist (or an album, playlist or artist name).
        kind: 'track', 'album', 'playlist', 'artist' or '' when not said.

    Returns:
        What happened, for the model: what is playing, or that only the search
        was opened and the user has to press play.

    Raises:
        SpotifyError: Spotify could not be started.
    """
    query = " ".join(query.split())[:MAX_QUERY]
    if not query:
        raise SpotifyError("nothing to play: the query is empty")
    kind = kind if kind in KINDS else ""

    # the web lookup and the start of the app run side by side
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        lookup = pool.submit(find_item, query, language, kind)
        launch()
        item = lookup.result()

    if item:
        found_kind, ident = item
        before = _now_playing()
        _open_uri(f"spotify:{found_kind}:{ident}")
        deadline = time.monotonic() + PLAY_WAIT_S
        while time.monotonic() < deadline:
            time.sleep(POLL_S)
            playing = _now_playing()
            if playing and playing != before:
                return f"DONE: the {found_kind} is playing now in Spotify ({playing})"
        return (f"DONE: the {found_kind} was opened in Spotify; the player did not report it yet. "
                "Say it was started and that the user should press play if there is no sound")
    _open_uri("spotify:search:" + urllib.parse.quote(query, safe=""))
    return ("PARTIAL: the exact item was not found, so only the search for it is open in Spotify. "
            "Say so: the user has to pick the result and press play")
