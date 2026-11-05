"""
ai_assistant.py
---------------
Prinny's local AI: the chat window, the conversation with the model and the
few actions the model can ask Prinny to do (see ai.py and ai_tools.py).

AssistantMixin is mixed into the Prinny widget and relies on its attributes
(config, _skins, _scale, _volume, _muted, _set_anim, ...).
"""

import time
from datetime import datetime

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

import ai
from ai_tools import build_tools
from utils import t


WALK_TO_TIMEOUT_S = 30
REACTION_MS       = 4500       # how long a mood animation lasts after an answer

# Mood of an answer (see ai.split_mood) -> the animation that plays
MOOD_ANIMATIONS = {"shrug": "shrug", "grimace": "grimace", "joy": "hype", "sulk": "fail"}
MAX_JUMPS         = 5

# Behaviour name (see ai_tools.BEHAVIORS) -> Prinny's forced state, the same ones as the right-click menu
BEHAVIOR_STATES = {
    "free": None, "stay_still": "idle", "keep_moving": "walk",
    "keep_busy": "inspect_menu", "express": "hype", "punish": "fail", "grimace": "grimace", "shrug": "shrug", "attack": "attack", "shock": "shock", "cry": "cry", "eat": "eat",
}

# Flag set while an animation plays, and the callback that ends it
ANIMATION_FLAGS = {
    "idle":    ("_idle_active",    "_end_idle"),
    "walk":    ("_walk_active",    "_end_walk"),
    "inspect": ("_inspect_active", "_end_inspect"),
    "hype":    ("_hype_active",    "_end_hype"),
    "fail":    ("_fail_active",    "_end_fail"),
}


class AssistantMixin:
    """Chat window, conversation and model-driven actions for Prinny."""

    # -----------------------------------------------------------------------
    # Chat
    # -----------------------------------------------------------------------

    def _init_assistant(self) -> None:
        self._chat_window  = None   # created on first use (see toggle_chat_window)
        self._chat_session = None

    # -----------------------------------------------------------------------
    # Animation that follows the conversation
    # -----------------------------------------------------------------------

    _reaction_anim  = None      # animation played over his usual behaviour, or None
    _reaction_busy  = False     # it is the "busy" one, kept until the answer arrives
    _reaction_token = 0

    def _can_react(self) -> bool:
        """False when he must not be interrupted: dragged, hidden, jumping, on his way somewhere or under an order."""
        return not (self._dragging or self._forced_state or self._goto_x is not None or self._jumping
                    or self._menu_active or self._silenced() or getattr(self, "_crying", False))

    def _start_reaction(self, anim: str, duration_ms: int | None) -> None:
        self._reaction_token += 1
        self._reaction_anim = anim
        self._set_anim(anim)
        if duration_ms:
            token = self._reaction_token
            QTimer.singleShot(duration_ms, lambda: self._end_reaction(token))

    def _end_reaction(self, token: int | None = None) -> None:
        if token is not None and token != self._reaction_token:
            return                                  # a newer reaction replaced this one
        self._reaction_anim = None
        self._reaction_busy = False
        if not self._dragging:
            self._set_anim("idle")

    def set_chat_busy(self, busy: bool) -> None:
        """He keeps busy (the inspection animation) while he works on a message of the chat."""
        if busy:
            if self._can_react():
                self._reaction_busy = True
                self._start_reaction("inspect", None)
        elif self._reaction_busy:
            self._end_reaction()

    def react_to_mood(self, mood: str) -> None:
        """Shrug, make a face, rejoice or sulk for a few seconds, as the answer said."""
        anim = MOOD_ANIMATIONS.get(mood)
        if anim and self._can_react():
            self._start_reaction(anim, REACTION_MS)

    def is_chat_window_visible(self) -> bool:
        return bool(self._chat_window) and self._chat_window.isVisible()

    def toggle_chat_window(self) -> None:
        """Open the chat with Prinny, or close it if it is already open."""
        if self.is_chat_window_visible():
            self._chat_window.hide()
            return

        from chat_window import ChatWindow
        if not self._chat_window:
            self._chat_session = ai.ChatSession(
                build_tools(self), self.config.get("ai_model"), self,
            )
            self._chat_window = ChatWindow(self.config, self._chat_session, self._ai_system_prompt,
                                           on_busy=self.set_chat_busy, on_mood=self.react_to_mood)
        self._chat_window.open(near=self)

    def _ai_system_prompt(self) -> str:
        """Prinny's character plus what he knows right now."""
        context = t("ai_context").format(
            time=datetime.now().strftime("%A %H:%M"),
            skin=self._current_skin, size=self._scale,
            volume=0 if self._muted else self._volume, behavior=self._behavior_name(),
        )
        return f"{t('ai_system_prompt')}\n{context}"

    # -----------------------------------------------------------------------
    # Actions asked by the model
    # -----------------------------------------------------------------------

    def perform_animation(self, name: str, seconds: float) -> None:
        """Play an animation for a few seconds, then go back to normal."""
        flag, end = ANIMATION_FLAGS[name]
        self._reset_behaviour_flags()
        setattr(self, flag, True)
        self._set_anim(name)
        QTimer.singleShot(int(seconds * 1000), getattr(self, end))

    def set_behavior(self, mode: str) -> None:
        """Keep Prinny in one behaviour until told otherwise (what the menu's Behavior submenu does)."""
        self._reset_behaviour_flags()
        self._forced_state = BEHAVIOR_STATES[mode]

    def _behavior_name(self) -> str:
        for name, state in BEHAVIOR_STATES.items():
            if state == self._forced_state:
                return name
        return "free"

    def walk_to(self, place: str) -> None:
        """Walk to the 'left' or 'right' edge or the 'center' of the current screen."""
        desktop = QApplication.desktop()
        area = desktop.availableGeometry(max(desktop.screenNumber(self), 0))
        x = {"left": area.left(), "right": area.right() - self.width(),
             "center": area.center().x() - self.width() // 2}[place]
        self._reset_behaviour_flags()
        self._goto_x        = x
        self._goto_deadline = time.monotonic() + WALK_TO_TIMEOUT_S
        self._walk_active   = True

    def jump(self, direction: str, times: int) -> None:
        """Jump on the spot ('up') or toward 'left' / 'right', `times` times in a row."""
        kept = self._forced_state if self._forced_state in ("idle", "walk") else None   # keep "stay still"
        self._reset_behaviour_flags()
        self._forced_state = kept
        self._jumps_left = min(max(times, 1), MAX_JUMPS) - 1
        self._jump_vx    = 0 if direction == "up" else None
        if direction != "up":
            self._direction = -1 if direction == "left" else 1
        self._start_jump()

    def _after_jump(self) -> None:
        """Called on landing: chain the next commanded jump, or go back to the usual jumps."""
        if self._jumps_left > 0:
            self._jumps_left -= 1
            self._start_jump()
        else:
            self._jump_vx = None

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self.config.set("muted", muted)
