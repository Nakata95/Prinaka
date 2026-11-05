"""
food.py
-------
A dish put on the desktop for Prinny: a bowl of ramen that drops from the top of the screen. He goes to it, lifts the
bowl in his raised hand (his "express yourself" animation), then eats (his "eat" animation) with the bowl in front of him;
the bowl is empty by the end, he puts it down and it is cleared away.

FoodMixin is mixed into the Prinny widget. It relies on WorldMixin (_hand_point, _on_ground), the reaction system of
AssistantMixin and the walk to a point (_goto_x). Everything is in memory: nothing is saved.
"""

import os
import time

from PyQt5.QtWidgets import QLabel, QWidget
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap

from utils import get_total_screen_rect, resource_path, t


FOOD_INTERVAL_MS = 30
GROUND_OFFSET    = 40          # same as Prinny: pixels above the bottom of the screen
DISHES = {                     # kind: (full picture, empty picture, drawing scale relative to Prinny's size setting)
    "ramen": ("bowl_full", "bowl_empty", 0.6),
    "ham":   ("ham_full", "ham_empty", 0.36),
}
GRAVITY          = 1900.0
REACH_PX         = 62          # centres closer than this, both on the ground: he picks the bowl up
LIFT_MS          = 1400        # the bowl held up in his raised hand
EAT_MS           = 3800        # he eats, the bowl in front of him
EMPTY_AT         = 0.5         # the bowl turns empty after this share of the meal
CLEAR_MS         = 2500        # the empty bowl stays on the ground this long
FACE_REL         = (0.50, 0.50)  # where the bowl is held while he eats, relative to his window (x mirrored when he faces right)


class BowlWidget(QWidget):
    """The bowl: a small click-through window with a full and an empty picture."""

    def __init__(self, full: QPixmap, empty: QPixmap):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._pix = {"full": full, "empty": empty}
        self._label = QLabel(self)
        self.resize(max(full.width(), empty.width()), max(full.height(), empty.height()))
        self._label.resize(self.size())
        self._label.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self.state = "full"
        self._label.setPixmap(full)
        self.x_pos = 0.0
        self.y_pos = 0.0
        self.vy = 0.0
        self.on_ground = False

    @property
    def cx(self) -> float:
        return self.x_pos + self.width() / 2

    def set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self._label.setPixmap(self._pix[state])

    def place_center(self, cx: float, cy: float) -> None:
        self.x_pos, self.y_pos = cx - self.width() / 2, cy - self.height() / 2
        self.move(int(round(self.x_pos)), int(round(self.y_pos)))

    def drop_from(self, cx: float, top: float) -> None:
        self.x_pos, self.y_pos = cx - self.width() / 2, top - self.height()
        self.vy, self.on_ground = 0.0, False
        self.move(int(round(self.x_pos)), int(round(self.y_pos)))

    def fall(self, dt: float, floor_line: float) -> None:
        if self.on_ground:
            return
        self.vy += GRAVITY * dt
        self.y_pos += self.vy * dt
        if self.y_pos + self.height() >= floor_line:
            self.y_pos, self.vy, self.on_ground = floor_line - self.height(), 0.0, True
        self.move(int(round(self.x_pos)), int(round(self.y_pos)))


class FoodMixin:
    """Prinny's side of the meal."""

    _dish_base = {}

    def _init_food(self) -> None:
        self._bowl       = None        # the BowlWidget on the desktop, or None
        self._meal       = None        # the meal in progress: {"phase", "t"}
        self._food_last  = time.monotonic()
        self._food_timer = QTimer(self)
        self._food_timer.timeout.connect(self._food_tick)

    # --- placing --------------------------------------------------------------

    def _bowl_pictures(self, kind: str = "ramen") -> tuple:
        names = DISHES[kind]
        if kind not in FoodMixin._dish_base:
            FoodMixin._dish_base[kind] = tuple(
                QPixmap(resource_path(os.path.join("assets", "entities", "food", f"{n}.png"))) for n in names[:2])
        k = names[2] * self._scale / 100
        return tuple(p.scaled(max(1, round(p.width() * k)), max(1, round(p.height() * k)), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                     for p in FoodMixin._dish_base[kind])

    def spawn_bowl(self, rng=None, kind=None) -> tuple:
        """Drop a dish (ramen or ham, random unless kind is given) from the top of the screen, far from Prinny. Returns (done, what happened, for the chat)."""
        import random
        rng = rng or random
        if self._bowl is not None:
            return False, "there is already a dish on the desktop"
        if self._fight is not None:
            return False, "Prinny is in the middle of a fight"
        rng_ = rng or random
        kind = kind if kind in DISHES else rng_.choice(list(DISHES))
        full, empty = self._bowl_pictures(kind)
        if full.isNull() or empty.isNull():
            return False, "the dish drawings are missing"
        area = get_total_screen_rect()
        px = self.x() + self.width() / 2
        far_left = px - area.left() > area.right() - px
        lo, hi = (area.left() + 60, px - 220) if far_left else (px + 220, area.right() - 60)
        if hi <= lo:
            lo, hi = area.left() + 60, area.right() - 60
        bowl = BowlWidget(full, empty)
        bowl.drop_from(rng.uniform(lo, max(lo, hi)), area.top())
        bowl.show()
        self._bowl = bowl
        self._food_last = time.monotonic()
        self._food_timer.start(FOOD_INTERVAL_MS)
        return True, ("a bowl of ramen" if kind == "ramen" else "a ham on a plate") + " was put on the desktop: Prinny goes to eat it"

    # --- the loop -------------------------------------------------------------

    def _food_tick(self) -> None:
        now = time.monotonic()
        dt, self._food_last = min(0.1, now - self._food_last), now
        bowl = self._bowl
        if bowl is None:
            self._food_timer.stop()
            return
        area = get_total_screen_rect()
        floor_line = area.bottom() - GROUND_OFFSET
        if self._silenced():                                       # hidden or a full-screen app: the dish waits out of sight
            bowl.hide()
            return
        if not bowl.isVisible():
            bowl.show()
        if self._meal is not None:
            self._meal_step(dt)
            return
        bowl.fall(dt, floor_line)
        if bowl.state == "empty":                                  # an empty bowl left on the ground: cleared away
            self._clear_left = getattr(self, "_clear_left", CLEAR_MS) - dt * 1000
            if self._clear_left <= 0:
                self._remove_bowl()
            return
        if not bowl.on_ground or not self._can_hunt():
            return
        if self._jumping or self._throw is not None or not self._on_ground(floor_line):
            return
        prinny_cx = self.x() + self.width() / 2
        s = self._scale / 100
        if abs(bowl.cx - prinny_cx) < REACH_PX * s:
            self._start_meal()
            return
        if not self._hunting:
            self._hunting = True
            self._reset_behaviour_flags()
        self._goto_x = int(min(max(bowl.cx - self.width() / 2, area.left()), area.right() - self.width()))
        self._goto_deadline = time.monotonic() + 2.0
        self._walk_active = True

    # --- the meal -------------------------------------------------------------

    def _start_meal(self) -> None:
        self._hunting, self._goto_x, self._walk_active = False, None, False
        self._direction = 1 if self._bowl.cx > self.x() + self.width() / 2 else -1
        self._meal = {"phase": "lift", "t": 0.0}
        self._start_reaction("hype", LIFT_MS)                      # his raised hand lifts the bowl
        self._bowl.raise_()

    def _face_point(self) -> tuple:
        fx = FACE_REL[0] if self._direction != 1 else 1 - FACE_REL[0]
        return self.x() + self.width() * fx, self.y() + self.height() * FACE_REL[1]

    def _meal_step(self, dt: float) -> None:
        m, bowl = self._meal, self._bowl
        m["t"] += dt * 1000
        if self._dragging:                                         # picked up by the user: the bowl drops where it is
            self._meal = None
            bowl.on_ground = False
            return
        if m["phase"] == "lift":
            hx, hy = self._hand_point()
            bowl.place_center(hx, hy - bowl.height() * 0.45)
            bowl.raise_()
            if m["t"] >= LIFT_MS:
                m.update(phase="eat", t=0.0)
                self._start_reaction("eat", EAT_MS)                # he starts to eat, the bowl up in front of him
                self._show_bubble(t("food_start"), 3000)
        elif m["phase"] == "eat":
            fx, fy = self._face_point()
            wobble = 4 * (self._frame % 2) * self._scale / 100     # the bowl moves with his gulps
            bowl.place_center(fx, fy - wobble)
            bowl.raise_()
            if m["t"] >= EMPTY_AT * EAT_MS:
                bowl.set_state("empty")
            if m["t"] >= EAT_MS:
                m.update(phase="put", t=0.0)
                bowl.y_pos = self.y() + self.height() * 0.55       # he puts it down in front of him
                bowl.vy, bowl.on_ground = 0.0, False
                self._clear_left = CLEAR_MS
                self._show_bubble(t("food_done"), 4000)
        elif m["phase"] == "put":
            bowl.fall(dt, get_total_screen_rect().bottom() - GROUND_OFFSET)
            if bowl.on_ground:
                self._meal = None

    def _remove_bowl(self) -> None:
        if self._bowl is not None:
            self._bowl.hide()
            self._bowl.close()
        self._bowl, self._meal = None, None
        self._food_timer.stop()
