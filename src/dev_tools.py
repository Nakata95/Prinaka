"""
dev_tools.py
------------
Helpers for someone who codes, kept out of prinny.py:

- git projects: Prinny looks at the projects the user registered, and says so
  when changes stay uncommitted for hours, commits are not pushed or the remote
  moved on (git_watch.py, read-only)
- reminders: "remind me in 25 minutes" rings with a bubble, a sound and a system
  notification (reminders.py, kept in memory only)

DevToolsMixin is mixed into the Prinny widget and relies on its attributes
(config, _show_bubble, _set_anim, _silenced, _busy_with_user, _tray, ...).
"""

import time

from PyQt5.QtWidgets import QFileDialog, QSystemTrayIcon
from PyQt5.QtCore import QTimer

import git_watch
from poller import BackgroundPoller
from reminders import Reminders
from utils import t


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GIT_INTERVAL_S      = 300
GIT_BUBBLE_MS       = 14000
REMINDER_BUBBLE_MS  = 20000
REMINDER_ANIM_MS    = 4000
MAX_PROJECTS        = 30


class DevToolsMixin:
    """Git watch and reminders for Prinny."""

    # -----------------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------------

    def _init_dev_tools(self) -> None:
        self._git_paths   = git_watch.parse_list(self.config.get("git_projects"))
        self._git_alerted = {}                  # (path, kind) -> count when it was said
        self._git_job     = git_watch.GitJob(self)
        self._git_job.done.connect(self._on_git_now)
        self._git_poller  = BackgroundPoller(self._read_git, GIT_INTERVAL_S, self, com=False)
        self._git_poller.updated.connect(self._on_git)
        self._refresh_git_poller()

        self._reminders = Reminders(self)
        self._reminders.due.connect(self._on_reminder)

    # -----------------------------------------------------------------------
    # Git projects
    # -----------------------------------------------------------------------

    def _refresh_git_poller(self) -> None:
        """Run the periodic look only if it is on, git is installed and there is a project."""
        self._git_poller.stop()
        if self.config.get("git_watch_enabled") and self._git_paths and git_watch.available():
            self._git_poller.start()

    def _read_git(self, cycle: int) -> dict:
        """Run in the background thread (see BackgroundPoller)."""
        return {"statuses": [git_watch.read(path) for path in list(self._git_paths)]}

    def _on_git(self, data: dict) -> None:
        """
        Say once per situation which project needs attention.

        A problem is reported once. It is reported again only when it gets worse
        (more commits not pushed, more commits to pull) or when it was solved and
        comes back; changes left uncommitted are reported once per stretch of work,
        however many files are added meanwhile.
        """
        if self._silenced() or self._busy_with_user():
            return                              # nothing is marked as said: it comes at the next look
        now = time.time()
        lines = []
        for status in data["statuses"]:
            found = {kind: (count, age) for kind, count, age in git_watch.alerts(status, now)}
            for key in [k for k in self._git_alerted if k[0] == status.path and k[1] not in found]:
                del self._git_alerted[key]      # solved: a new occurrence will be reported
            for kind, (count, age) in found.items():
                key = (status.path, kind)
                said = self._git_alerted.get(key)
                if said is not None and (kind == "dirty" or count <= said):
                    continue
                self._git_alerted[key] = count
                lines.append(t(f"git_alert_{kind}").format(
                    project=status.name, count=count, age=self._age_text(age), branch=status.branch,
                    upstream=status.upstream))
        if lines:
            self._show_bubble("\n".join(lines), GIT_BUBBLE_MS)

    def _age_text(self, seconds: float) -> str:
        seconds = int(seconds)
        if seconds < 3600:
            return t("git_age_min").format(n=max(1, seconds // 60))
        if seconds < 86400:
            return t("git_age_hour").format(n=seconds // 3600)
        return t("git_age_day").format(n=seconds // 86400)

    def git_paths(self) -> list:
        return list(self._git_paths)

    def add_git_project_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("git_pick_folder"))
        if not folder:
            return
        folder = folder.replace("/", "\\")
        if not git_watch.is_project(folder):
            self._show_bubble(t("git_not_a_project"), 6000)
            return
        if folder in self._git_paths:
            return
        if len(self._git_paths) >= MAX_PROJECTS:
            self._show_bubble(t("git_too_many"), 6000)
            return
        self._git_paths.append(folder)
        self.config.set("git_projects", git_watch.join_list(self._git_paths))
        self._refresh_git_poller()
        self._show_bubble(t("git_added").format(project=folder.rstrip("\\/").rsplit("\\", 1)[-1]), 5000)

    def remove_git_project(self, path: str) -> None:
        if path in self._git_paths:
            self._git_paths.remove(path)
            self.config.set("git_projects", git_watch.join_list(self._git_paths))
            self._git_alerted = {k: v for k, v in self._git_alerted.items() if k[0] != path}
            self._refresh_git_poller()

    def set_git_watch_enabled(self, enabled: bool) -> None:
        self.config.set("git_watch_enabled", enabled)
        self._refresh_git_poller()

    def show_git_now(self) -> None:
        """Look at every project right now and show the result in a bubble."""
        if not git_watch.available():
            self._show_bubble(t("git_missing"), 6000)
        elif not self._git_paths:
            self._show_bubble(t("git_none"), 6000)
        else:
            self._git_job.start(list(self._git_paths))

    def _on_git_now(self, statuses: list) -> None:
        lines = []
        for s in statuses:
            if s.error:
                lines.append(t("git_line_error").format(project=s.name, error=s.error))
                continue
            bits = [t("git_line_changed").format(count=s.changed) if s.changed else t("git_line_clean")]
            if s.ahead:
                bits.append(t("git_line_ahead").format(count=s.ahead))
            if s.behind:
                bits.append(t("git_line_behind").format(count=s.behind))
            lines.append(f"{s.name} ({s.branch}) : " + ", ".join(bits))
        self._show_bubble("\n".join(lines), 12000)

    # -----------------------------------------------------------------------
    # Reminders
    # -----------------------------------------------------------------------

    def _on_reminder(self, label: str) -> None:
        text = t("reminder_ring").format(label=label) if label else t("reminder_ring_plain")
        tray = getattr(self, "_tray", None)
        if tray:                                # seen even when Prinny is hidden or a game runs full screen
            tray.showMessage("Prinaka", text, QSystemTrayIcon.Information, 10000)
        if self._silenced():
            return
        self._show_bubble(text, REMINDER_BUBBLE_MS)
        self._play_drag_sound()
        self._set_anim("hype")
        self._hype_active = True
        QTimer.singleShot(REMINDER_ANIM_MS, self._end_hype)

    # -----------------------------------------------------------------------
    # Menu
    # -----------------------------------------------------------------------

    def _build_git_menu(self, menu) -> dict:
        """Submenu: git watch on/off, add or remove a project, look now."""
        handlers = {}
        sub = menu.addMenu(t("menu_git"))

        if not git_watch.available():
            sub.addAction(t("git_missing")).setEnabled(False)
            return handlers

        watch = self._check_action(sub, t("menu_git_watch"), self.config.get("git_watch_enabled"))
        handlers[watch] = lambda a=watch: self.set_git_watch_enabled(a.isChecked())
        sub.addSeparator()

        add = sub.addAction(t("menu_git_add"))
        handlers[add] = self.add_git_project_dialog
        if self._git_paths:
            now = sub.addAction(t("menu_git_now"))
            handlers[now] = self.show_git_now
            remove_menu = sub.addMenu(t("menu_git_remove"))
            for path in self._git_paths:
                action = remove_menu.addAction(path.rstrip("\\/").rsplit("\\", 1)[-1] or path)
                action.setToolTip(path)
                handlers[action] = lambda p=path: self.remove_git_project(p)
        return handlers
