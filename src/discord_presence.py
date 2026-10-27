"""
discord_presence.py
-------------------
Discord Rich Presence manager for Prinaka.

Handles profile storage, validation, the connection to Discord via
pypresence and automatic reconnection when Discord is closed/reopened.

Network calls run in background threads so the UI never freezes.
Results are reported through the `state_changed` signal.
"""

import json
import os
import threading
import time

import psutil
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from pypresence import Presence

from utils import resource_path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRESENCES_FILE = os.path.join("assets", "presences.json")

WATCHDOG_INTERVAL_MS = 15000   # Discord limits presence updates to 1 per 15 s
MAX_TEXT_LENGTH      = 128     # details / state / tooltips
MAX_LABEL_LENGTH     = 32      # button label

# All known Discord process names across stable, PTB and Canary builds
DISCORD_PROCESSES = {
    "discord.exe",
    "discordptb.exe",
    "discordcanary.exe",
    "discord",
    "discordptb",
    "discordcanary",
}

# status message -> (locale key, is_success)
STATUS_TEXTS = {
    "activated":         ("presence_activated",         True),
    "stopped":           ("presence_stopped",           False),
    "discord_closed":    ("presence_discord_closed",    False),
    "no_client_id":      ("presence_no_client_id",      False),
    "invalid_client_id": ("presence_invalid_client_id", False),
}


# ---------------------------------------------------------------------------
# Profile storage
# ---------------------------------------------------------------------------

def load_profiles() -> list:
    """Return the saved profiles (empty list if the file is missing or invalid)."""
    try:
        with open(resource_path(PRESENCES_FILE), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_profiles(profiles: list) -> None:
    """Write the profiles list to assets/presences.json."""
    path = resource_path(PRESENCES_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=4, ensure_ascii=False)


def find_profile(name: str) -> dict | None:
    """Return the saved profile called `name`, or None."""
    for profile in load_profiles():
        if profile.get("name") == name:
            return profile
    return None


def unique_name(name: str, profiles: list, ignore_index: int = -1) -> str:
    """
    Return `name`, suffixed with ' (2)', ' (3)'... if already used.

    Args:
        name: Wanted profile name.
        profiles: Existing profiles.
        ignore_index: Index of the profile being renamed (not counted as a clash).
    """
    taken = {p.get("name") for i, p in enumerate(profiles) if i != ignore_index}
    if name not in taken:
        return name
    n = 2
    while f"{name} ({n})" in taken:
        n += 1
    return f"{name} ({n})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_discord_running() -> bool:
    """
    Check whether Discord is currently running.

    Detects stable, PTB and Canary builds.

    Returns:
        True if a Discord process is found, False otherwise.
    """
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in DISCORD_PROCESSES:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def validate_profile(profile: dict) -> tuple[str, dict] | None:
    """
    Check a profile against Discord's constraints.

    Returns:
        None if the profile is valid, otherwise (locale_key, format_args)
        describing the first problem found.
    """
    for key in ("details", "state"):
        if len(profile.get(key, "")) == 1:   # Discord rejects 1-char strings
            return "presence_too_short", {"field": key}

    for i in (1, 2):
        label = profile.get(f"button{i}_label", "")
        url   = profile.get(f"button{i}_url",   "")
        if bool(label) != bool(url):
            return "presence_button_incomplete", {"n": i}
        if url and not url.lower().startswith(("http://", "https://")):
            return "presence_bad_url", {"n": i}

    return None


# ---------------------------------------------------------------------------
# Presence manager
# ---------------------------------------------------------------------------

class DiscordPresenceManager(QObject):
    """
    Manages a single Discord Rich Presence connection.

    Once `activate_async` has been called, the manager keeps the presence
    alive: if Discord is closed it waits, and re-applies the profile as soon
    as Discord is back. `stop` cancels that.

    Signals:
        state_changed(is_active, message): emitted from any thread after
            every change. `message` is a key of STATUS_TEXTS or a raw
            error string.
    """

    state_changed = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._rpc:        Presence | None = None
        self._client_id:  str | None      = None
        self._start_time: float | None    = None
        self._wanted:     dict | None     = None   # profile the user wants active
        self._lock = threading.Lock()
        self._busy = False

        self.is_active:    bool = False
        self.profile_name: str  = ""

        self._watchdog = QTimer(self)
        self._watchdog.timeout.connect(self._on_watchdog)
        self._watchdog.start(WATCHDOG_INTERVAL_MS)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    @property
    def is_waiting(self) -> bool:
        """True when a profile is wanted but not applied yet (Discord closed)."""
        return self._wanted is not None and not self.is_active

    @property
    def start_time(self) -> float | None:
        """Timestamp the elapsed timer started at, or None if no timer is shown."""
        return self._start_time

    @property
    def is_busy(self) -> bool:
        """True while a connection attempt is running."""
        return self._busy

    def activate_async(self, profile: dict) -> None:
        """Connect and apply `profile` in the background."""
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._activate_job, args=(profile,), daemon=True).start()

    def stop(self) -> None:
        """Clear the presence and stop keeping it alive."""
        with self._lock:
            self._wanted = None
            self._start_time = None
            self._disconnect()
        self.state_changed.emit(False, "stopped")

    def shutdown(self) -> None:
        """Close the connection on app exit, without emitting any signal."""
        self._watchdog.stop()
        with self._lock:
            self._wanted = None
            self._disconnect()

    # -----------------------------------------------------------------------
    # Background jobs
    # -----------------------------------------------------------------------

    def _activate_job(self, profile: dict) -> None:
        try:
            with self._lock:
                self._wanted     = None
                self._start_time = None   # fresh activation restarts the timer
                ok, msg = self._connect_and_update(profile)
            self.state_changed.emit(ok, msg)
        finally:
            self._busy = False

    def _on_watchdog(self) -> None:
        if self._wanted is None or self._busy:
            return
        self._busy = True
        threading.Thread(target=self._watchdog_job, daemon=True).start()

    def _watchdog_job(self) -> None:
        try:
            with self._lock:
                profile = self._wanted
                if profile is None:
                    return
                was_active = self.is_active

                if not is_discord_running():
                    self._disconnect(keep_wanted=True)
                    if was_active:
                        self.state_changed.emit(False, "discord_closed")
                    return

                # Re-sending the payload doubles as a connection check
                ok, msg = self._connect_and_update(profile)
                if ok != was_active:
                    self.state_changed.emit(ok, msg)
        finally:
            self._busy = False

    # -----------------------------------------------------------------------
    # Connection (call with the lock held)
    # -----------------------------------------------------------------------

    def _connect_and_update(self, profile: dict) -> tuple[bool, str]:
        client_id = profile.get("client_id", "").strip()
        if not client_id:
            self._wanted = None
            return False, "no_client_id"

        self._wanted = profile   # keep trying even if Discord is closed

        if not is_discord_running():
            self._disconnect(keep_wanted=True)
            return False, "discord_closed"

        try:
            if self._rpc and self._client_id != client_id:
                self._disconnect(keep_wanted=True)

            if not self._rpc:
                rpc = Presence(client_id)
                rpc.connect()
                self._rpc       = rpc
                self._client_id = client_id

            self._send(profile)

        except Exception as e:
            # Broken pipe or stale connection: drop it and retry once from scratch
            self._disconnect(keep_wanted=True)
            try:
                rpc = Presence(client_id)
                rpc.connect()
                self._rpc       = rpc
                self._client_id = client_id
                self._send(profile)
            except Exception as e2:
                if type(e2).__name__ == "InvalidID":
                    self._wanted = None
                    return False, "invalid_client_id"
                return False, str(e2) or str(e)

        self.is_active    = True
        self.profile_name = profile.get("name", "")
        return True, "activated"

    def _send(self, profile: dict) -> None:
        if profile.get("show_timer"):
            if self._start_time is None:
                self._start_time = time.time()
        else:
            self._start_time = None

        buttons = []
        for i in (1, 2):
            label = profile.get(f"button{i}_label", "").strip()[:MAX_LABEL_LENGTH]
            url   = profile.get(f"button{i}_url",   "").strip()
            if label and url:
                buttons.append({"label": label, "url": url})

        def text(key: str) -> str | None:
            return profile.get(key, "").strip()[:MAX_TEXT_LENGTH] or None

        self._rpc.update(
            details     = text("details"),
            state       = text("state"),
            large_image = profile.get("large_image", "").strip() or None,
            large_text  = text("large_text"),
            small_image = profile.get("small_image", "").strip() or None,
            small_text  = text("small_text"),
            start       = self._start_time,
            buttons     = buttons or None,
        )

    def _disconnect(self, keep_wanted: bool = False) -> None:
        try:
            if self._rpc:
                self._rpc.close()
        except Exception:
            pass
        finally:
            self._rpc       = None
            self._client_id = None
            self.is_active  = False
            if not keep_wanted:
                self.profile_name = ""
