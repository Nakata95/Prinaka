"""
features.py
-----------
Optional behaviours of Prinny, kept out of prinny.py:

- random quotes and contextual reactions (quotes.py, reactions.py)
- system alerts: RAM, CPU, disk, temperature, battery (alerts.py)
- Windows Defender relay: detections and file scans (defender.py)
- do-not-disturb during full-screen apps (fullscreen.py)
- system tray icon (tray.py) and launch at Windows startup (startup.py)

FeaturesMixin is mixed into the Prinny widget and relies on its attributes
(config, _show_bubble, _set_anim, ...). Each feature also contributes its
submenu to the right-click menu: the builders return a dict mapping each
clickable QAction to the callable to run once the menu closes.
"""

import os
import random
from datetime import datetime

import psutil
from PyQt5 import sip
from PyQt5.QtWidgets import QAction, QApplication, QFileDialog, QSystemTrayIcon
from PyQt5.QtCore import QTimer

import defender
import startup
from alerts import RULES, AlertMonitor, get_rule
from fullscreen import is_fullscreen_busy
from listeners import get_click_count, get_key_count
from poller import BackgroundPoller
from quotes import get_quote
from reactions import ReactionEngine
from tray import TrayIcon
from utils import t


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# frequency level -> (min, max) delay in ms between two random quotes
QUOTE_INTERVALS = {
    "low":    (120000, 180000),
    "normal": (45000,  75000),
    "high":   (30000,  40000),
}

QUOTE_DURATION_MS    = 8000
REACTION_DURATION_MS = 7000

ALERT_INTERVAL_MS      = 10000
DEFENDER_INTERVAL_S    = 60
THREAT_DURATION_MS     = 15000
REACTION_INTERVAL_MS   = 20000
FULLSCREEN_INTERVAL_MS = 2000
GREETING_DELAY_MS      = 5000


class FeaturesMixin:
    """Quotes, reactions, alerts, do-not-disturb, tray and startup for Prinny."""

    # -----------------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------------

    def _init_features(self) -> None:
        """Create the timers and helpers. Call once the widget is built."""
        self._network_window = None   # created on first use (see toggle_network_window)
        self._player_window  = None   # created on first use (see toggle_player_window)
        self._dnd_active  = False   # a full-screen app is running
        self._user_hidden = False   # hidden by the user from the tray

        # --- Random quotes ---
        self._speech_timer = QTimer(self)
        self._speech_timer.setSingleShot(True)
        self._speech_timer.timeout.connect(self._show_random_quote)
        self._schedule_quote()

        # --- Contextual reactions ---
        self._reactions = ReactionEngine()
        self._reaction_timer = QTimer(self)
        self._reaction_timer.timeout.connect(self._check_reactions)
        self._reaction_timer.start(REACTION_INTERVAL_MS)
        QTimer.singleShot(GREETING_DELAY_MS, self._check_reactions)

        # --- System alerts ---
        self._alert_monitor = AlertMonitor(self.config)
        self._alert_timer = QTimer(self)
        self._alert_timer.timeout.connect(self._check_alerts)
        self._alert_timer.start(ALERT_INTERVAL_MS)

        # --- Windows Defender relay ---
        self._seen_detections   = set()    # keys already reported
        self._defender_ready    = False    # first reading done
        self._defender_available = None    # None = not known yet
        self._threat_lines      = []       # active threats, shown in the alert bubble
        self._threat_new        = False    # a threat appeared since the last alert check
        self._scan_job          = None
        self._defender_poller = BackgroundPoller(self._read_defender, DEFENDER_INTERVAL_S, self, com=False)
        self._defender_poller.updated.connect(self._on_defender)
        if self.config.get("defender_enabled"):
            self._defender_poller.start()

        # --- Do not disturb ---
        self._fullscreen_timer = QTimer(self)
        self._fullscreen_timer.timeout.connect(self._check_fullscreen)
        self._fullscreen_timer.start(FULLSCREEN_INTERVAL_MS)

        # --- Tray icon ---
        self._tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = TrayIcon(self)
            self._tray.show()
            QApplication.instance().aboutToQuit.connect(self._tray.hide)

        startup.refresh()   # keep the startup entry pointing at this install

    def _silenced(self) -> bool:
        """True when Prinny must not show bubbles or play sounds."""
        return self._dnd_active or self._user_hidden

    def _alert_bubble_alive(self) -> bool:
        return bool(self._alert_bubble) and not sip.isdeleted(self._alert_bubble)

    def _busy_with_user(self) -> bool:
        """True while the user is interacting with Prinny (menu, drag)."""
        return bool(getattr(self, "_menu_active", False) or getattr(self, "_dragging", False))

    # -----------------------------------------------------------------------
    # Random quotes
    # -----------------------------------------------------------------------

    def _schedule_quote(self) -> None:
        low, high = QUOTE_INTERVALS.get(self.config.get("quotes_frequency"), QUOTE_INTERVALS["normal"])
        self._speech_timer.start(random.randint(low, high))

    def _show_random_quote(self) -> None:
        """Show a random quote, unless quotes are off or Prinny is busy."""
        self._schedule_quote()

        if not self.config.get("quotes_enabled") or self._silenced() or self._busy_with_user():
            return

        quote = get_quote("random")
        if not quote:
            return

        self._show_bubble(quote, duration_ms=QUOTE_DURATION_MS)
        self._set_anim("hype")
        self._hype_active = True
        QTimer.singleShot(QUOTE_DURATION_MS, self._end_hype)

    def set_quotes_enabled(self, enabled: bool) -> None:
        self.config.set("quotes_enabled", enabled)
        if not enabled:
            self._close_bubble()

    def set_quotes_frequency(self, level: str) -> None:
        self.config.set("quotes_frequency", level)
        self._schedule_quote()

    # -----------------------------------------------------------------------
    # Contextual reactions
    # -----------------------------------------------------------------------

    def _check_reactions(self) -> None:
        """Ask the reaction engine whether Prinny has something to say."""
        if not self.config.get("reactions_enabled") or self._silenced() or self._busy_with_user():
            return

        battery = psutil.sensors_battery()
        battery_state = (battery.percent, battery.power_plugged) if battery else None

        reaction = self._reactions.check(
            datetime.now(), get_click_count(), get_key_count(), battery_state
        )
        if not reaction:
            return

        category, values = reaction
        text = get_quote(category, **values)
        if text:
            self._show_bubble(text, duration_ms=REACTION_DURATION_MS)

    def set_reactions_enabled(self, enabled: bool) -> None:
        self.config.set("reactions_enabled", enabled)

    # -----------------------------------------------------------------------
    # System alerts
    # -----------------------------------------------------------------------

    def _check_alerts(self) -> None:
        """Read the enabled alerts and show one persistent bubble listing them."""
        active, new = self._alert_monitor.check()

        if self._silenced():
            return   # the bubble is rebuilt when Prinny is visible again

        if not active and not self._threat_lines:
            self._close_alert_bubble()
            return

        message = "\n".join(
            [t(rule.message_key).format(value=int(value), percent=int(value)) for rule, value in active]
            + self._threat_lines
        )

        if new or self._threat_new:
            self._threat_new = False
            self._play_drag_sound()
            self._set_anim("fail")
            self._fail_active = True
            QTimer.singleShot(3000, self._end_fail)

        if self._alert_bubble_alive():
            self._alert_bubble.update_text(message)
            self._alert_bubble.update_position(self)
        else:
            self._show_alert_bubble(message)

    def set_alert_enabled(self, key: str, enabled: bool) -> None:
        self.config.set(get_rule(key).enabled_key, enabled)
        self._alert_monitor.clear(key)
        self._check_alerts()

    def set_alert_threshold(self, key: str, value: int) -> None:
        self.config.set(get_rule(key).threshold_key, value)
        self._alert_monitor.clear(key)
        self._check_alerts()

    # -----------------------------------------------------------------------
    # Windows Defender relay
    # -----------------------------------------------------------------------

    def _read_defender(self, cycle: int) -> dict:
        """Run in the background thread (see BackgroundPoller)."""
        return {"detections": defender.read_detections()}

    def _on_defender(self, data: dict) -> None:
        """Report new detections; keep still-active threats in the alert bubble."""
        detections = data["detections"]
        self._defender_available = detections is not None
        if detections is None:
            self._threat_lines = []
            self._check_alerts()
            return

        first = not self._defender_ready
        self._defender_ready = True

        fresh = defender.new_detections(self._seen_detections, detections)
        if first:   # the history is old news: only threats still present matter
            fresh = [d for d in fresh if d.active]

        self._threat_lines = [
            t("sec_threat_line").format(name=d.title, target=d.target).strip()
            for d in detections if d.active
        ]
        self._threat_new = any(d.active for d in fresh)

        for d in fresh:
            key = "sec_threat" if d.active else "sec_blocked"
            self._notify_security(t(key).format(name=d.title, target=d.target))
            if not d.active:
                self._show_bubble(t("sec_blocked").format(name=d.title, target=d.target), THREAT_DURATION_MS)
        self._check_alerts()

    def _notify_security(self, text: str) -> None:
        """System notification, so a threat is seen even when Prinny is hidden."""
        tray = getattr(self, "_tray", None)
        if tray:
            tray.showMessage("Prinaka", text, QSystemTrayIcon.Warning, 10000)

    def set_defender_enabled(self, enabled: bool) -> None:
        self.config.set("defender_enabled", enabled)
        if enabled:
            self._defender_poller.start()
        else:
            self._defender_poller.stop()
            self._threat_lines = []
            self._check_alerts()

    def scan_file_dialog(self) -> None:
        """Ask for a file and have Defender scan it."""
        if self._scan_job and self._scan_job.running:
            self._show_bubble(t("sec_scan_busy"), 4000)
            return

        path, _ = QFileDialog.getOpenFileName(self, t("sec_pick_file"))
        if not path:
            return

        if not self._scan_job:
            self._scan_job = defender.ScanJob(self)
            self._scan_job.finished.connect(self._on_scan_finished)
        self._show_bubble(t("sec_scanning").format(file=os.path.basename(path)), 5000)
        self._scan_job.start(path)

    def _on_scan_finished(self, result: dict) -> None:
        name = os.path.basename(result["path"])
        if result["status"] == "clean":
            self._show_bubble(t("sec_scan_clean").format(file=name), 8000)
        elif result["status"] == "threat":
            text = t("sec_scan_threat").format(file=name, name=", ".join(result["threats"]))
            self._show_bubble(text, THREAT_DURATION_MS)
            self._notify_security(text)
            self._set_anim("fail")
            self._fail_active = True
            QTimer.singleShot(3000, self._end_fail)
        else:
            text = t("sec_scan_error").format(file=name)
            if result.get("reason"):
                text += f"\n{result['reason'][:160]}"
            self._show_bubble(text, 12000)

    def open_windows_security(self) -> None:
        try:
            os.startfile("windowsdefender:")
        except OSError:
            pass

    # -----------------------------------------------------------------------
    # Do not disturb / visibility
    # -----------------------------------------------------------------------

    def _check_fullscreen(self) -> None:
        busy = bool(self.config.get("dnd_fullscreen")) and is_fullscreen_busy()
        if busy != self._dnd_active:
            self._set_dnd(busy)

    def _set_dnd(self, active: bool) -> None:
        """Hide Prinny and stay silent during a full-screen app, restore afterwards."""
        self._dnd_active = active
        if active:
            self._close_bubble()
            self._close_alert_bubble()
            self.hide()
        else:
            if not self._user_hidden:
                self.show()
            self._check_alerts()

    def set_dnd_enabled(self, enabled: bool) -> None:
        self.config.set("dnd_fullscreen", enabled)
        self._check_fullscreen()

    def is_user_hidden(self) -> bool:
        return self._user_hidden

    def toggle_visibility(self) -> None:
        """Show or hide Prinny (tray icon)."""
        self._user_hidden = not self._user_hidden
        if self._user_hidden:
            self._close_bubble()
            self._close_alert_bubble()
            self.hide()
        elif not self._dnd_active:
            self.show()
            self._check_alerts()

    # -----------------------------------------------------------------------
    # Tray / startup helpers
    # -----------------------------------------------------------------------

    def current_icon(self):
        """First idle frame of the current skin, used by the tray icon."""
        frames = self._sprites.get("idle") or []
        return frames[0] if frames else None

    def _refresh_tray_icon(self) -> None:
        tray = getattr(self, "_tray", None)   # skin is first applied before the tray exists
        if tray:
            tray.refresh_icon()

    def is_network_window_visible(self) -> bool:
        return bool(self._network_window) and self._network_window.isVisible()

    def toggle_network_window(self) -> None:
        """
        Open the compact network overlay, or close it if it is already open.

        It is opened without taking the focus so a running game keeps it.
        """
        if self.is_network_window_visible():
            self._network_window.hide()
            return

        from network_window import NetworkWindow
        if not self._network_window:
            self._network_window = NetworkWindow(self.config)
        self._network_window.open(near=self, activate=False)

    def is_player_window_visible(self) -> bool:
        return bool(self._player_window) and self._player_window.isVisible()

    def toggle_player_window(self) -> None:
        """Open the mini media player, or close it if it is already open."""
        if self.is_player_window_visible():
            self._player_window.hide()
            return

        from player_window import PlayerWindow
        if not self._player_window:
            self._player_window = PlayerWindow(self.config)
        self._player_window.open(near=self, activate=False)

    def quit_app(self) -> None:
        QApplication.quit()

    def set_startup(self, enabled: bool) -> None:
        ok = startup.enable() if enabled else startup.disable()
        if not ok:
            self._show_bubble(t("startup_error"))

    # -----------------------------------------------------------------------
    # Menus
    # -----------------------------------------------------------------------

    def _check_action(self, parent_menu, text: str, checked: bool) -> QAction:
        action = QAction(text, self, checkable=True)
        action.setChecked(checked)
        parent_menu.addAction(action)
        return action

    def _build_dialogue_menu(self, menu) -> dict:
        """Submenu: quotes, reactions and how often Prinny talks."""
        handlers = {}
        sub = menu.addMenu(t("menu_dialogues"))

        quotes = self._check_action(sub, t("menu_quotes"), self.config.get("quotes_enabled"))
        handlers[quotes] = lambda a=quotes: self.set_quotes_enabled(a.isChecked())

        reactions = self._check_action(sub, t("menu_reactions"), self.config.get("reactions_enabled"))
        handlers[reactions] = lambda a=reactions: self.set_reactions_enabled(a.isChecked())

        sub.addSeparator()
        freq_menu = sub.addMenu(t("menu_frequency"))
        current = self.config.get("quotes_frequency")
        for level in QUOTE_INTERVALS:
            action = self._check_action(freq_menu, t(f"menu_freq_{level}"), level == current)
            handlers[action] = lambda l=level: self.set_quotes_frequency(l)

        return handlers

    def _build_alert_menu(self, menu) -> dict:
        """Submenu: one entry per alert with enable switch and threshold presets."""
        handlers = {}
        sub = menu.addMenu(t("menu_alerts"))

        for rule in RULES:
            if not rule.available():
                continue

            threshold = self.config.get(rule.threshold_key)
            title = f"{rule.icon} {t(rule.name_key)}  ({rule.symbol}{threshold}{rule.unit})"
            if self._alert_monitor.last_values.get(rule.key, 0) is None and self.config.get(rule.enabled_key):
                title += f"  {t('menu_alert_unavailable')}"
            rule_menu = sub.addMenu(title)

            enabled = self._check_action(rule_menu, t("menu_alert_enabled"), self.config.get(rule.enabled_key))
            handlers[enabled] = lambda r=rule, a=enabled: self.set_alert_enabled(r.key, a.isChecked())

            rule_menu.addSeparator()
            for preset in rule.presets:
                action = self._check_action(
                    rule_menu, f"{rule.symbol} {preset}{rule.unit}", preset == threshold
                )
                handlers[action] = lambda r=rule, v=preset: self.set_alert_threshold(r.key, v)

        return handlers

    def _build_security_menu(self, menu) -> dict:
        """Submenu: Defender relay, scan a file, open Windows Security."""
        handlers = {}
        sub = menu.addMenu(t("menu_security"))

        if self._defender_available is False and self.config.get("defender_enabled"):
            sub.addAction(t("sec_unavailable")).setEnabled(False)
            sub.addSeparator()

        watch = self._check_action(sub, t("menu_defender_watch"), self.config.get("defender_enabled"))
        handlers[watch] = lambda a=watch: self.set_defender_enabled(a.isChecked())

        sub.addSeparator()
        scan = sub.addAction(t("menu_scan_file"))
        handlers[scan] = self.scan_file_dialog
        open_security = sub.addAction(t("menu_open_security"))
        handlers[open_security] = self.open_windows_security

        return handlers

    def _build_options_menu(self, menu) -> dict:
        """Submenu: launch at startup and do-not-disturb."""
        handlers = {}
        sub = menu.addMenu(t("menu_options"))

        if startup.AVAILABLE:
            at_startup = self._check_action(sub, t("menu_startup"), startup.is_enabled())
            handlers[at_startup] = lambda a=at_startup: self.set_startup(a.isChecked())

        dnd = self._check_action(sub, t("menu_dnd"), self.config.get("dnd_fullscreen"))
        handlers[dnd] = lambda a=dnd: self.set_dnd_enabled(a.isChecked())

        return handlers
