"""
prinny.py
---------
Main Prinny widget for Prinaka.

Handles:
- Sprite animation state machine (idle, walk, drag, fall, inspect, hype, fail)
- Physics (gravity, jumping, multi-monitor boundaries)
- Drag and drop with mouse
- Sound playback
- Speech bubbles (random quotes + media notifications)
- Right-click context menu
- Skin and language switching
- Credits dialog
"""

import os
import random
import json

from PyQt5 import sip
from PyQt5.QtWidgets import (
    QWidget, QLabel, QMenu, QSlider, QWidgetAction, QHBoxLayout,
    QDialog, QVBoxLayout, QPushButton, QApplication, QAction
)
from PyQt5.QtCore import Qt, QTimer, QUrl, QPoint
from PyQt5.QtGui import QPixmap, QTransform
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

from utils import resource_path, load_sprites, get_total_screen_rect, t, load_language, get_current_language
from config import ConfigManager
from media import get_current_media_info
from speech_bubble import SpeechBubble
from features import FeaturesMixin
from discord_presence import (
    DiscordPresenceManager, STATUS_TEXTS, find_profile, load_profiles,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANIMATIONS      = ["idle", "walk", "drag", "fall", "inspect", "hype", "fail"]
TIMER_INTERVAL  = 90        # ms between each game loop tick
ANIM_INTERVAL   = 50        # ms between each animation frame
GRAVITY         = 10
WALK_SPEED      = 5
MAX_FALL_SPEED  = 90
FALL_SMOOTH     = 0.5
JUMP_VELOCITY   = -50
GROUND_OFFSET   = 40        # px above the bottom of the screen

# Discord Rich Presence is finished but hidden for now: set to True to bring
# back the menu entry, the autostart and the background reconnection.
PRESENCE_ENABLED = False


# ---------------------------------------------------------------------------
# Prinny widget
# ---------------------------------------------------------------------------

class Prinny(FeaturesMixin, QWidget):
    """
    The main animated desktop buddy widget.

    Prinny roams the desktop autonomously, reacts to user interaction,
    plays sounds, and shows speech bubbles.
    """

    # --- Skin sizes (width, height) in pixels ---
    SKIN_SIZES = {
        "default":   (165, 165),
        "pink":      (165, 165),
        "red":       (165, 165),
        "cake":      (165, 165),
        "gentleman": (165, 165),
        "kurtis":    (165, 165),
        "summer":    (165, 165),
    }

    # --- System alert thresholds ---
    MAX_RAM_PERCENT = 85
    MAX_CPU_PERCENT = 90

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # --- Config ---
        self.config = ConfigManager()

        # --- Language ---
        load_language(self.config.get("language"))

        # --- Skins ---
        self._skins = {name: self._load_skin(f"assets/sprites/{name}") for name in self.SKIN_SIZES}
        self._current_skin = self.config.get("skin")
        if self._current_skin not in self._skins:
            self._current_skin = "default"

        self._sprites = self._skins[self._current_skin]
        self._apply_skin_size()

        # --- Label (displays current frame) ---
        self._label = QLabel(self)
        self._label.resize(self.size())

        # --- Animation state ---
        self._current_anim  = "idle"
        self._frame         = 0
        self._anim_timers   = {anim: 0 for anim in ANIMATIONS}

        if self._sprites.get("idle"):
            self._label.setPixmap(self._sprites["idle"][0])
        self._refresh_tray_icon()

        # --- Movement ---
        self.move(500, 200)
        self._direction = random.choice([-1, 1])

        # --- Physics ---
        self._vy        = 0.0
        self._vy_jump   = 0.0
        self._jumping   = False

        # --- Behaviour flags ---
        self._dragging       = False
        self._drag_prev_pos  = QPoint()
        self._menu_active    = False
        self._forced_state   = None

        self._walk_active    = False
        self._idle_active    = False
        self._inspect_active = False
        self._hype_active    = False
        self._fail_active    = False

        # --- Behaviour probabilities ---
        self._jump_chance         = 0.25
        self._idle_min            = 5000
        self._idle_max            = 6000
        self._walk_min            = 4000
        self._walk_max            = 7000
        self._inspect_min         = 6000
        self._inspect_max         = 8000
        self._hype_min            = 3000
        self._hype_max            = 3000

        # --- Sound ---
        self._volume             = self.config.get("volume")
        self._muted              = self.config.get("muted")
        self._drag_sounds        = []
        self._drag_cooldown      = 0
        self._drag_cooldown_max  = 8 * (1000 // TIMER_INTERVAL)
        self._load_sounds()

        # --- Speech bubbles ---
        self._bubble         = None
        self._alert_bubble   = None   # bulle persistante RAM (séparée des bulles normales)

        # --- Media tracking ---
        self._media_enabled = self.config.get("media_enabled")
        self._last_media    = None

        self._media_timer = QTimer(self)
        self._media_timer.timeout.connect(self._check_media)
        self._media_timer.start(5000)

        # --- Quotes, reactions, alerts, do-not-disturb, tray (features.py) ---
        self._init_features()

        # --- Info window (lazy init) ---
        self._info_window = None

        # --- Discord Rich Presence ---
        self._presence_manager = None
        self._presence_window  = None
        self._preview_popup    = None
        if PRESENCE_ENABLED:
            self._presence_manager = DiscordPresenceManager(self)
            self._presence_manager.state_changed.connect(self._on_presence_state)
            QApplication.instance().aboutToQuit.connect(self._presence_manager.shutdown)

            if self.config.get("presence_autostart"):
                QTimer.singleShot(3000, self._autostart_presence)

        # --- Main loop ---
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(TIMER_INTERVAL)


    # -----------------------------------------------------------------------
    # Skin
    # -----------------------------------------------------------------------

    def _load_skin(self, base_folder: str) -> dict:
        """
        Load all animation frames for a skin.

        Args:
            base_folder: Path to the skin folder (e.g. 'assets/sprites/default').

        Returns:
            Dict mapping animation name to list of QPixmap frames.
        """
        return {
            anim: load_sprites(os.path.join(base_folder, anim))
            for anim in ANIMATIONS
        }

    def _apply_skin_size(self) -> None:
        """Resize the widget to match the current skin's dimensions."""
        w, h = self.SKIN_SIZES.get(self._current_skin, (165, 165))
        self.resize(w, h)
        if hasattr(self, "_label"):
            self._label.resize(w, h)

    def change_skin(self, skin_name: str) -> None:
        """
        Switch to a different skin and reload sounds.

        Args:
            skin_name: Key of the skin to apply (e.g. 'pink').
        """
        if skin_name not in self._skins:
            return

        self._current_skin = skin_name
        self._sprites      = self._skins[skin_name]
        self.config.set("skin", skin_name)

        self._apply_skin_size()
        self._load_sounds()
        self._set_anim("idle")
        self._frame = 0

        if self._sprites.get("idle"):
            self._label.setPixmap(self._sprites["idle"][0])


    # -----------------------------------------------------------------------
    # Sounds
    # -----------------------------------------------------------------------

    def _load_sounds(self) -> None:
        """
        Load drag sounds for the current skin.

        Falls back to the 'default' sound folder if none exists for the skin.
        """
        self._drag_sounds = []

        folder = resource_path(os.path.join("assets", "sounds", self._current_skin))
        if not os.path.exists(folder):
            folder = resource_path(os.path.join("assets", "sounds", "default"))

        if not os.path.exists(folder):
            return

        for f in sorted(os.listdir(folder)):
            if f.endswith(".wav"):
                player = QMediaPlayer()
                player.setMedia(QMediaContent(
                    QUrl.fromLocalFile(os.path.join(folder, f))
                ))
                player.setVolume(self._volume)
                self._drag_sounds.append(player)

    def _play_drag_sound(self) -> None:
        """Play a random drag sound if not muted and cooldown has elapsed."""
        if self._muted or not self._drag_sounds or self._drag_cooldown > 0:
            return

        sound = random.choice(self._drag_sounds)
        sound.stop()
        sound.setVolume(self._volume)
        sound.play()
        self._drag_cooldown = self._drag_cooldown_max

    def change_volume(self, value: int) -> None:
        """
        Update the volume level and save it.

        Args:
            value: Volume level between 0 and 100.
        """
        self._volume = value
        self.config.set("volume", value)


    # -----------------------------------------------------------------------
    # Animation
    # -----------------------------------------------------------------------

    def _set_anim(self, anim: str) -> None:
        """
        Switch to a new animation and reset its frame counter.

        Args:
            anim: Animation name (e.g. 'walk', 'idle').
        """
        if self._current_anim != anim:
            self._current_anim = anim
            self._frame        = 0

    def _update_frame(self) -> None:
        """Advance the animation by one frame if enough time has elapsed."""
        frames = self._sprites.get(self._current_anim, [])
        if not frames:
            return

        self._anim_timers[self._current_anim] += TIMER_INTERVAL

        if self._anim_timers[self._current_anim] >= ANIM_INTERVAL:
            self._anim_timers[self._current_anim] = 0
            self._frame = (self._frame + 1) % len(frames)

            pixmap = frames[self._frame]

            # Flip horizontally when moving right (except during drag)
            if self._direction == 1 and self._current_anim != "drag":
                pixmap = pixmap.transformed(QTransform().scale(-1, 1))

            self._label.setPixmap(pixmap)


    # -----------------------------------------------------------------------
    # Physics & state machine
    # -----------------------------------------------------------------------

    def _update(self) -> None:
        """
        Main game loop tick.

        Called every TIMER_INTERVAL ms. Handles physics, animation state
        transitions, movement, and drag sound cooldown.
        """
        total_rect = get_total_screen_rect()
        ground_y   = total_rect.bottom() - self.height() - GROUND_OFFSET

        # Cooldown
        if self._drag_cooldown > 0:
            self._drag_cooldown -= 1

        # --- Dragging overrides everything ---
        if self._dragging:
            self._reset_behaviour_flags()
            self._set_anim("drag")
            self._play_drag_sound()
            self._update_frame()
            return

        # --- Forced / active behaviour animations ---
        if self._any_behaviour_active():
            self._apply_behaviour_anim()
            self._apply_gravity(ground_y)
            self._update_frame()
            return

        # --- Physics: jumping ---
        if self._jumping:
            self._vy_jump += GRAVITY * FALL_SMOOTH
            self._vy_jump  = min(self._vy_jump, MAX_FALL_SPEED)

            new_y = self.y() + self._vy_jump
            new_x = self.x() + (WALK_SPEED * 4) * self._direction
            new_x = max(total_rect.left(), min(new_x, total_rect.right() - self.width()))

            if new_y >= ground_y:
                new_y         = ground_y
                self._vy_jump = 0
                self._jumping = False

            self.move(int(new_x), int(new_y))
            self._set_anim("fall")

        # --- Physics: falling ---
        elif self.y() < ground_y:
            self._vy  += GRAVITY * FALL_SMOOTH
            self._vy   = min(self._vy, MAX_FALL_SPEED)
            self.move(self.x(), int(min(self.y() + self._vy, ground_y)))
            self._set_anim("fall")

        # --- On the ground: autonomous behaviour ---
        else:
            self._vy = 0

            if self._forced_state == "idle":
                self._set_anim("idle")

            elif self._forced_state == "walk" or self._walk_active:
                self._walk_step(total_rect)

            else:
                self._pick_random_behaviour()

        self._update_frame()

    def _apply_gravity(self, ground_y: int) -> None:
        """Apply gravity when a behaviour animation is active but Prinny is airborne."""
        if self.y() < ground_y:
            self._vy += GRAVITY * FALL_SMOOTH
            self._vy  = min(self._vy, MAX_FALL_SPEED)
            self.move(self.x(), int(min(self.y() + self._vy, ground_y)))

    def _walk_step(self, total_rect) -> None:
        """Move Prinny one step in the current direction, bouncing off screen edges."""
        self._set_anim("walk")
        new_x = self.x() + WALK_SPEED * self._direction

        if new_x <= total_rect.left():
            new_x            = total_rect.left()
            self._direction  = 1
        elif new_x >= total_rect.right() - self.width():
            new_x            = total_rect.right() - self.width()
            self._direction  = -1

        self.move(int(new_x), self.y())

    def _pick_random_behaviour(self) -> None:
        """Randomly choose the next autonomous behaviour."""
        r = random.random()

        if r < 0.3:
            self._set_anim("idle")
            self._idle_active = True
            QTimer.singleShot(
                random.randint(self._idle_min, self._idle_max),
                self._end_idle
            )

        elif r < 0.5:
            self._set_anim("inspect")
            self._inspect_active = True
            QTimer.singleShot(
                random.randint(self._inspect_min, self._inspect_max),
                self._end_inspect
            )

        elif r < 0.6:
            self._set_anim("hype")
            self._hype_active = True
            QTimer.singleShot(
                random.randint(self._hype_min, self._hype_max),
                self._end_hype
            )

        else:
            self._set_anim("walk")
            self._walk_active = True
            QTimer.singleShot(
                random.randint(self._walk_min, self._walk_max),
                self._end_walk
            )
            # Chance to jump at the start of a walk
            if random.random() < self._jump_chance:
                self._jumping  = True
                self._vy_jump  = JUMP_VELOCITY

    def _any_behaviour_active(self) -> bool:
        """Return True if any forced or active behaviour is currently running."""
        return any([
            self._inspect_active,
            self._hype_active,
            self._fail_active,
            self._idle_active,
            self._menu_active,
            self._forced_state in ("inspect_menu", "fail", "hype"),
        ])

    def _apply_behaviour_anim(self) -> None:
        """Set the correct animation for the currently active behaviour."""
        if self._inspect_active or self._forced_state == "inspect_menu":
            self._set_anim("inspect")
        elif self._hype_active or self._forced_state == "hype":
            self._set_anim("hype")
        elif self._fail_active or self._forced_state == "fail":
            self._set_anim("fail")
        elif self._idle_active:
            self._set_anim("idle")

    def _reset_behaviour_flags(self) -> None:
        """Cancel all active behaviour flags."""
        self._walk_active    = False
        self._idle_active    = False
        self._inspect_active = False
        self._hype_active    = False
        self._fail_active    = False
        self._forced_state   = None


    # -----------------------------------------------------------------------
    # Behaviour end callbacks
    # -----------------------------------------------------------------------

    def _end_walk(self) -> None:
        self._walk_active = False
        if not self._dragging:
            self._set_anim("idle")

    def _end_idle(self) -> None:
        self._idle_active = False
        if not self._dragging:
            self._set_anim("idle")

    def _end_inspect(self) -> None:
        self._inspect_active = False
        if not self._dragging:
            self._set_anim("idle")

    def _end_hype(self) -> None:
        self._hype_active = False
        if not self._dragging:
            self._set_anim("idle")

    def _end_fail(self) -> None:
        self._fail_active = False
        if not self._dragging:
            self._set_anim("idle")


    # -----------------------------------------------------------------------
    # Mouse events
    # -----------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging      = True
            self._drag_prev_pos = event.globalPos()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return

        delta           = event.globalPos() - self._drag_prev_pos
        self._drag_prev_pos = event.globalPos()

        total_rect = get_total_screen_rect()
        new_x = max(total_rect.left(), min(self.x() + delta.x(), total_rect.right()  - self.width()))
        new_y = max(total_rect.top(),  min(self.y() + delta.y(), total_rect.bottom() - self.height()))
        self.move(int(new_x), int(new_y))

        self._direction = 1 if delta.x() > 0 else -1

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._set_anim("fall")

    def moveEvent(self, event) -> None:
        """Keep all speech bubbles above Prinny when he moves."""
        super().moveEvent(event)
        if self._bubble and not sip.isdeleted(self._bubble):
            self._bubble.update_position(self)
        if self._alert_bubble and not sip.isdeleted(self._alert_bubble):
            self._alert_bubble.update_position(self)


    # -----------------------------------------------------------------------
    # Speech bubbles
    # -----------------------------------------------------------------------

    def _close_bubble(self) -> None:
        """Safely close and clear the current speech bubble."""
        if self._bubble and not sip.isdeleted(self._bubble):
            self._bubble.close()
        self._bubble = None

    def _show_bubble(self, text: str, duration_ms: int = 5000) -> None:
        """
        Display a temporary speech bubble above Prinny's head.

        If a RAM alert bubble is active, it is hidden during the
        temporary bubble and restored automatically afterward.

        Args:
            text: Text to display in the bubble.
            duration_ms: How long to show the bubble in milliseconds.
        """
        if self._silenced():
            return

        self._close_bubble()

        # Cacher temporairement la bulle d alerte si elle est active
        if self._alert_bubble and not sip.isdeleted(self._alert_bubble):
            self._alert_bubble.hide()

        self._bubble = SpeechBubble(text, self)
        self._bubble.update_position(self)
        self._bubble.show()

        def _restore_alert():
            self._close_bubble()
            # Remettre la bulle d alerte si elle existe encore
            if self._alert_bubble and not sip.isdeleted(self._alert_bubble):
                self._alert_bubble.show()
                self._alert_bubble.update_position(self)

        QTimer.singleShot(duration_ms, _restore_alert)

    # -----------------------------------------------------------------------
    # Media tracking
    # -----------------------------------------------------------------------

    def _check_media(self) -> None:
        """Check if the playing media has changed and show a bubble if so."""
        if not self._media_enabled:
            return

        current = get_current_media_info()
        if current and current != self._last_media:
            self._last_media = current
            self._show_bubble(f"🎵 {current}", duration_ms=5000)


    def _show_alert_bubble(self, text: str) -> None:
        """
        Show the persistent alert bubble above Prinny.

        Unlike normal bubbles, this one stays until RAM drops below threshold.

        Args:
            text: Alert message to display.
        """
        self._close_alert_bubble()
        self._alert_bubble = SpeechBubble(text, self)
        self._alert_bubble.update_position(self)
        self._alert_bubble.show()

    def _close_alert_bubble(self) -> None:
        """Safely close and clear the persistent alert bubble."""
        if self._alert_bubble and not sip.isdeleted(self._alert_bubble):
            self._alert_bubble.close()
        self._alert_bubble = None

    # -----------------------------------------------------------------------
    # Context menu
    # -----------------------------------------------------------------------

    def contextMenuEvent(self, event) -> None:
        """Build and display the right-click context menu."""
        self._menu_active = True

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1b1b1b;
                border: 1px solid #444;
                border-radius: 10px;
                padding: 6px;
            }
            QMenu::item {
                padding: 9px 30px;
                color: #e0e0e0;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background-color: #3a3a3a;
            }
            QMenu::item:disabled {
                color: #777;
            }
            QMenu::separator {
                height: 1px;
                background: #333;
                margin: 5px 10px;
            }
        """)

        # --- Actions ---
        info_action = menu.addAction(t("menu_sys_info"))
        menu.addSeparator()

        # Behavior submenu (the forced state is checked)
        behavior_actions = {}
        behavior_menu = menu.addMenu(t("menu_behavior"))
        for key, state in (
            ("menu_free_action", None),
            ("menu_stay_idle",   "idle"),
            ("menu_walk_only",   "walk"),
            ("menu_keep_busy",   "inspect_menu"),
            ("menu_express",     "hype"),
            ("menu_punish",      "fail"),
        ):
            action = QAction(t(key), self, checkable=True)
            action.setChecked(self._forced_state == state)
            behavior_menu.addAction(action)
            behavior_actions[action] = state
        handlers = {}
        handlers.update(self._build_dialogue_menu(menu))
        handlers.update(self._build_alert_menu(menu))
        menu.addSeparator()

        # Media toggle
        media_action = QAction(t("menu_show_media"), self, checkable=True)
        media_action.setChecked(self._media_enabled)
        menu.addAction(media_action)

        # Mute toggle
        mute_label  = t("menu_mute") if not self._muted else t("menu_unmute")
        mute_action = menu.addAction(mute_label)

        # Volume row: icon, slider, live percentage
        volume_box = QWidget()
        volume_box.setStyleSheet("background: transparent; color: #e0e0e0;")
        volume_row = QHBoxLayout(volume_box)
        volume_row.setContentsMargins(30, 4, 30, 4)
        volume_icon  = QLabel("🔊")
        volume_value = QLabel(f"{self._volume}%")
        volume_value.setMinimumWidth(40)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(self._volume)
        slider.valueChanged.connect(self.change_volume)
        slider.valueChanged.connect(lambda v: volume_value.setText(f"{v}%"))
        volume_row.addWidget(volume_icon)
        volume_row.addWidget(slider, 1)
        volume_row.addWidget(volume_value)
        slider_action = QWidgetAction(menu)
        slider_action.setDefaultWidget(volume_box)
        menu.addAction(slider_action)
        menu.addSeparator()

        # Skin submenu (current skin checked)
        skin_menu = menu.addMenu(t("menu_change_skin"))
        for skin_name in self._skins:
            action = QAction(skin_name.capitalize(), self, checkable=True)
            action.setChecked(skin_name == self._current_skin)
            action.triggered.connect(lambda checked, s=skin_name: self.change_skin(s))
            skin_menu.addAction(action)

        # Language submenu (current language checked)
        lang_menu = menu.addMenu(t("menu_language"))
        for code, label in [("en", "English"), ("fr", "Français")]:
            action = QAction(label, self, checkable=True)
            action.setChecked(code == get_current_language())
            action.triggered.connect(lambda checked, l=code: self._change_language(l))
            lang_menu.addAction(action)

        handlers.update(self._build_options_menu(menu))
        if PRESENCE_ENABLED:
            handlers.update(self._build_presence_menu(menu))
        menu.addSeparator()
        credits_action = menu.addAction(t("menu_credits"))
        quit_action    = menu.addAction(t("menu_quit"))

        # --- Show menu ---
        chosen = menu.exec_(event.globalPos())

        self._dragging = False
        self._set_anim("fail")

        # --- Handle choice ---
        if chosen == info_action:
            self._show_info_window()
        elif chosen in behavior_actions:
            self._forced_state = behavior_actions[chosen]
        elif chosen == mute_action:
            self._muted = not self._muted
            self.config.set("muted", self._muted)
        elif chosen == media_action:
            self._media_enabled = media_action.isChecked()
            self.config.set("media_enabled", self._media_enabled)
        elif chosen in handlers:
            handlers[chosen]()
        elif chosen == credits_action:
            self._show_credits()
        elif chosen == quit_action:
            self.quit_app()

        self._menu_active = False


    # -----------------------------------------------------------------------
    # Info window
    # -----------------------------------------------------------------------

    def _show_info_window(self) -> None:
        """Open the system info window (lazy initialisation)."""
        from info_window import InfoWindow
        if not self._info_window:
            self._info_window = InfoWindow(self.config)
        self._info_window.show()
        self._info_window.raise_()


    # -----------------------------------------------------------------------
    # Language
    # -----------------------------------------------------------------------

    def _change_language(self, lang: str) -> None:
        """
        Switch the application language and save the preference.

        Args:
            lang: Language code ('en' or 'fr').
        """
        load_language(lang)
        self.config.set("language", lang)


    # -----------------------------------------------------------------------
    # Discord Rich Presence window
    # -----------------------------------------------------------------------

    def _build_presence_menu(self, menu) -> dict:
        """
        Add the Discord Rich Presence submenu to `menu`.

        Lists the saved profiles for one-click switching, plus stop,
        autostart and the manager window.

        Returns:
            Dict mapping each clickable QAction to the callable to run.
        """
        manager = self._presence_manager
        handlers = {}

        title = t("menu_discord")
        if manager.is_active:
            title += f"  🟢 {manager.profile_name}"
        elif manager.is_waiting:
            title += "  🟡"
        sub = menu.addMenu(title)

        profiles = load_profiles()
        if not profiles:
            sub.addAction(t("menu_discord_empty")).setEnabled(False)
        for profile in profiles:
            name   = profile.get("name") or "—"
            action = QAction(name, self, checkable=True)
            action.setChecked(manager.is_active and manager.profile_name == name)
            sub.addAction(action)
            handlers[action] = lambda p=profile: self._activate_presence(p)

        preview_menu = sub.addMenu(t("menu_discord_preview"))
        preview_menu.setEnabled(bool(profiles))
        for profile in profiles:
            action = preview_menu.addAction(profile.get("name") or "—")
            handlers[action] = lambda p=profile: self._show_presence_preview(p)

        sub.addSeparator()
        stop_action = sub.addAction(t("menu_discord_stop"))
        stop_action.setEnabled(manager.is_active or manager.is_waiting)
        handlers[stop_action] = manager.stop

        autostart_action = QAction(t("menu_discord_autostart"), self, checkable=True)
        autostart_action.setChecked(self.config.get("presence_autostart"))
        sub.addAction(autostart_action)
        handlers[autostart_action] = lambda: self.config.set(
            "presence_autostart", autostart_action.isChecked()
        )

        sub.addSeparator()
        manage_action = sub.addAction(t("menu_discord_manage"))
        handlers[manage_action] = self._show_presence_window

        return handlers

    def _activate_presence(self, profile: dict) -> None:
        """Apply a saved presence profile (from the right-click menu)."""
        self._presence_manager.activate_async(profile)

    def _autostart_presence(self) -> None:
        """Re-apply the last active presence profile at launch."""
        name = self.config.get("presence_last_profile")
        profile = find_profile(name) if name else None
        if profile:
            self._presence_manager.activate_async(profile)

    def _on_presence_state(self, active: bool, message: str) -> None:
        """React to presence changes: remember the profile and tell the user."""
        manager = self._presence_manager
        if active:
            self.config.set("presence_last_profile", manager.profile_name)
            self._show_bubble(t("presence_bubble_on").format(name=manager.profile_name))
        elif message == "stopped":
            self.config.set("presence_last_profile", "")
        elif message in STATUS_TEXTS:
            self._show_bubble(t(STATUS_TEXTS[message][0]))
        else:
            self._show_bubble(t("presence_error").format(error=message))

    def _show_presence_preview(self, profile: dict) -> None:
        """Show a popup with what Discord displays for `profile`."""
        from presence_window import PreviewPopup
        if not self._preview_popup:
            self._preview_popup = PreviewPopup(self._presence_manager)
        self._preview_popup.set_profile(profile)
        self._preview_popup.show()
        self._preview_popup.raise_()

    def _show_presence_window(self) -> None:
        """Open the Discord Rich Presence manager window."""
        from presence_window import PresenceWindow
        if not self._presence_window:
            self._presence_window = PresenceWindow(self._presence_manager)
        self._presence_window.show()
        self._presence_window.raise_()

    # -----------------------------------------------------------------------
    # Credits
    # -----------------------------------------------------------------------

    def _show_credits(self) -> None:
        """Display the credits dialog."""
        dlg = QDialog(self)
        dlg.setWindowTitle(t("credits_title"))
        dlg.setFixedSize(300, 400)

        layout = QVBoxLayout(dlg)

        image_path = resource_path("assets/credits2.png")
        if os.path.exists(image_path):
            img_label = QLabel()
            img_label.setPixmap(
                QPixmap(image_path).scaledToWidth(280, Qt.SmoothTransformation)
            )
            layout.addWidget(img_label)

        from PyQt5.QtCore import Qt as QtCore_Qt
        text_label = QLabel(t("credits_text"))
        text_label.setAlignment(QtCore_Qt.AlignCenter)
        layout.addWidget(text_label)

        close_btn = QPushButton(t("credits_close"))
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)

        dlg.exec_()