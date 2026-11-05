"""
git_watch.py
------------
Read-only look at the git projects the user registered (see dev_tools.py).

Only `git status` and `git log` are run, without a shell, with fixed arguments;
the only thing that varies is the folder, which comes from the user's own list.
Nothing is ever changed: no commit, no fetch, no checkout, no index refresh
(--no-optional-locks), and `core.fsmonitor` is switched off because a repository
can name a program there that `git status` would otherwise start.

"Behind" is counted from the last fetch the user did: nothing is downloaded.
"""

import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field

from PyQt5.QtCore import QObject, pyqtSignal


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GIT_TIMEOUT_S   = 10
MAX_FILES       = 300             # changed files whose age is looked at
MAX_COMMITS     = 3
SUBJECT_MAX     = 70
NO_WINDOW       = getattr(subprocess, "CREATE_NO_WINDOW", 0)

DIRTY_AFTER_S    = 3 * 3600       # changes left uncommitted this long are worth a reminder
UNPUSHED_AFTER_S = 2 * 3600       # the same for commits not pushed

GIT = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.quotepath=false"]
_BRANCH = re.compile(r"^## (?P<branch>.+?)(?:\.\.\.(?P<upstream>\S+))?(?: \[(?P<track>[^\]]*)\])?$")


def available() -> bool:
    return shutil.which("git") is not None


@dataclass
class Status:
    """What `git status` and `git log` say about one project."""
    name: str
    path: str
    branch: str = ""
    upstream: str = ""
    changed: int = 0                 # modified, added, deleted, untracked files
    dirty_since: float | None = None # oldest modification time among them (epoch seconds)
    ahead: int = 0                   # commits not pushed
    behind: int = 0                  # commits on the remote not here (as of the last fetch)
    last_commit: float | None = None # time of the last commit (epoch seconds)
    commits: list = field(default_factory=list)
    error: str = ""


def is_project(path: str) -> bool:
    """True for a folder that is the root of a git working tree."""
    return os.path.isdir(path) and os.path.exists(os.path.join(path, ".git"))


def _git(path: str, *args: str) -> str:
    result = subprocess.run(
        [*GIT, "-C", path, *args], capture_output=True, timeout=GIT_TIMEOUT_S, stdin=subprocess.DEVNULL,
        creationflags=NO_WINDOW, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        lines = result.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise OSError(lines[-1] if lines else "git failed")
    return result.stdout.decode("utf-8", errors="replace")


def _track(text: str) -> tuple:
    """(ahead, behind) from '[ahead 2, behind 1]'."""
    ahead = re.search(r"ahead (\d+)", text or "")
    behind = re.search(r"behind (\d+)", text or "")
    return (int(ahead.group(1)) if ahead else 0, int(behind.group(1)) if behind else 0)


def read(path: str) -> Status:
    """Look at one project. Never raises: a failure is reported in Status.error."""
    status = Status(name=os.path.basename(os.path.normpath(path)) or path, path=path)
    if not is_project(path):
        status.error = "not a git project"
        return status
    try:
        lines = _git(path, "status", "--porcelain=v1", "-b").splitlines()
        match = _BRANCH.match(lines[0]) if lines else None
        if match:
            status.branch = match.group("branch")
            status.upstream = match.group("upstream") or ""
            status.ahead, status.behind = _track(match.group("track"))
        files = [line[3:].split(" -> ")[-1].strip('"') for line in lines[1:] if len(line) > 3]
        status.changed = len(files)
        times = []
        for name in files[:MAX_FILES]:
            try:
                times.append(os.stat(os.path.join(path, name)).st_mtime)
            except OSError:
                pass                       # deleted file: no age
        status.dirty_since = min(times) if times else None

        try:
            log = _git(path, "log", f"-{MAX_COMMITS}", "--format=%ct\t%h %s").splitlines()
        except OSError:
            log = []                       # no commit yet
        if log:
            status.last_commit = float(log[0].split("\t")[0])
            status.commits = [line.split("\t", 1)[1][:SUBJECT_MAX] for line in log if "\t" in line]
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError) as e:
        status.error = str(e)[:120]
    return status


def alerts(status: Status, now: float | None = None) -> list:
    """
    What deserves a reminder, as (kind, count, age_seconds) tuples.

    kind is 'dirty' (changes not committed for a long time), 'unpushed'
    (commits not pushed for a long time) or 'behind' (the remote moved on).
    """
    now = time.time() if now is None else now
    found = []
    if status.error:
        return found
    if status.changed and status.dirty_since and now - status.dirty_since >= DIRTY_AFTER_S:
        found.append(("dirty", status.changed, now - status.dirty_since))
    if status.ahead and status.last_commit and now - status.last_commit >= UNPUSHED_AFTER_S:
        found.append(("unpushed", status.ahead, now - status.last_commit))
    if status.behind:
        found.append(("behind", status.behind, 0))
    return found


def summary(status: Status, now: float | None = None) -> str:
    """One project in plain words (English), for the model and the log of the chat."""
    now = time.time() if now is None else now
    if status.error:
        return f"{status.name}: cannot be read ({status.error})"
    parts = [f"{status.name} (branch {status.branch or '?'}{', tracks ' + status.upstream if status.upstream else ', no remote branch'})"]
    if status.changed:
        since = f", oldest change {_age(now - status.dirty_since)} ago" if status.dirty_since else ""
        parts.append(f"{status.changed} changed or new files{since}")
    else:
        parts.append("clean, nothing to commit")
    if status.ahead:
        parts.append(f"{status.ahead} commits not pushed")
    if status.behind:
        parts.append(f"{status.behind} commits to pull (as of the last fetch)")
    text = "; ".join(parts)
    if status.commits:
        text += ". Last commits: " + " | ".join(status.commits)
    return text


def _age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 3600:
        return f"{max(1, seconds // 60)} min"
    if seconds < 86400:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} d"


def parse_list(text: str) -> list:
    """The projects stored in the settings: paths separated by '|' (never valid in a Windows path)."""
    return [p for p in (text or "").split("|") if p.strip()]


def join_list(paths: list) -> str:
    return "|".join(paths)


class GitJob(QObject):
    """Reads some projects in a background thread; `done` carries the list of Status."""

    done = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = False

    def start(self, paths: list) -> None:
        if self.running:
            return
        self.running = True

        def work() -> None:
            statuses = [read(p) for p in paths]
            self.running = False
            self.done.emit(statuses)

        threading.Thread(target=work, daemon=True).start()
