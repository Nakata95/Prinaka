"""
world.py
--------
Things placed on the desktop that Prinny goes after. For now: a fish.

The fish is a small transparent window of its own, like Prinny, with a little physics and a will of its own:
it runs away from Prinny, slower than he runs, but it jumps high and often to get over him. When Prinny touches
it on the ground he cheers with the fish held up in his raised hand (his "express yourself" animation), then
puts it in his bag (his "keep busy" animation).

WorldMixin is mixed into the Prinny widget. It relies on its attributes (_walk_step machinery through _goto_x,
_start_reaction, _reaction_anim, _sprites, _direction, _show_bubble...). Everything is in memory: nothing is saved.
"""

import json
import os
import random
import time

from PyQt5.QtWidgets import QLabel, QWidget
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QPixmap, QTransform

from utils import get_total_screen_rect, load_sprites, resource_path, t


# ---------------------------------------------------------------------------
# Constants (distances in pixels at Prinny's 100% size, speeds in pixels per second)
# ---------------------------------------------------------------------------

WORLD_INTERVAL_MS = 30
GROUND_OFFSET     = 40          # same as Prinny: pixels above the bottom of the screen
MAX_FISH          = 2
FISH_SCALE        = 0.7         # size of the fish relative to its drawing, times Prinny's size setting
FISH_ANIMATIONS   = ("wait", "walk", "attack", "jump")
ANIM_FRAME_MS     = 110

GRAVITY_FALL      = 1900.0      # a fish dropped from the top of the screen
FLEE_RANGE        = 420         # it runs away when Prinny is closer than this
FLEE_SPEED        = 80          # slower than Prinny, who runs at about 155
JUMP_RANGE        = 120         # it jumps over him when he is this close...
JUMP_RATE         = 3.0         # ...with this chance per second (more often than not before he arrives)
OVER_DISTANCE     = 170         # it lands this far past Prinny
JUMP_APEX         = 240         # height of a jump over him, higher than Prinny
JUMP_TIME         = 0.9
HOP_RATE          = 0.9         # small hops while running away, per second
HOP_DISTANCE      = 130
HOP_APEX          = 110
HOP_TIME          = 0.55
LAND_COOLDOWN     = 0.35        # seconds on the ground after a landing: the moment he can catch it
CRY_AFTER_S       = 6.0         # a fish held over him this long makes him cry
CRY_RANGE         = 190         # horizontal distance under which the fish is "over him"
THROW_MAX         = 1600        # fastest throw, pixels per second
THROW_WINDOW_S    = 0.12        # the throw speed is the mouse speed over the last moments
EDGE_MARGIN       = 110         # cornered against the side of the screen: it jumps over him at once

CATCH_DISTANCE    = 62          # centres closer than this, both on the ground: caught
HOLD_MS           = 2600        # Prinny cheers with the fish held up
STORE_MS          = 750         # the fish goes into the bag
KEEP_MS           = 2800        # Prinny keeps busy with his bag (includes STORE_MS)
BAG_REL           = (0.30, 0.74)     # the bag, relative to his window (x mirrored when he faces right)
FLAME_WIDTH_PX    = 34          # width of a flame over an eye, at Prinny's 100% size (it covers 98% of the eye)
FLAME_CONTENT_W   = 59          # width of the flame drawing itself, in the flame images
FLAME_BASE        = (45, 107)   # where the flame starts, in the flame images (bottom centre)
FLAME_DROP        = 12          # the flame starts this many pixels below the centre of the eye
FLAME_MS          = 90          # a new flame image
FLAME_ANIMATIONS  = ("idle", "walk", "inspect", "grimace", "shrug", "fall")
HAND_FROM_SPRITE  = 0.45         # the raised hand is the highest point of the left part of the hype frame


class FishEntity(QWidget):
    """
    A fish on the desktop.

    Args:
        frames: {animation: [QPixmap]}, drawn facing left, already scaled.
        factor: the scale applied to the frames (to size the distances).
        rng: random generator (a seeded one makes tests repeatable).
    """

    def __init__(self, frames: dict, factor: float, rng=None):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.OpenHandCursor)
        self._label = QLabel(self)
        self.frames  = frames
        self.factor  = factor
        self.rng     = rng or random
        self.mode    = "free"            # free, dragged (by the mouse), held, storing
        self._grab   = QPoint()          # where on the fish the mouse took it
        self._trail  = []                # (time, x, y) of the mouse while dragging, to throw the fish
        self.x_pos   = 0.0               # top-left of the window, in floats
        self.y_pos   = 0.0
        self.vx      = 0.0
        self.vy      = 0.0
        self.gravity = GRAVITY_FALL
        self.on_ground = False
        self.cooldown  = 0.0
        self.facing    = -1              # -1: faces left like the drawing, +1: mirrored
        self.zoom      = 1.0
        self.anim      = "wait"
        self.frame     = 0
        self._anim_ms  = 0.0
        self._shown    = (None, None, None)
        w, h = self.base_size()
        self.resize(w, h)
        self._render()

    # --- geometry -----------------------------------------------------------

    def base_size(self) -> tuple:
        first = self.frames["wait"][0]
        return first.width(), first.height()

    @property
    def cx(self) -> float:
        return self.x_pos + self.width() / 2

    @property
    def cy(self) -> float:
        return self.y_pos + self.height() / 2

    def place_center(self, cx: float, cy: float) -> None:
        self.x_pos, self.y_pos = cx - self.width() / 2, cy - self.height() / 2
        self.move(int(round(self.x_pos)), int(round(self.y_pos)))

    # --- drawing ------------------------------------------------------------

    def _render(self) -> None:
        key = (self.anim, self.frame, (self.facing, round(self.zoom, 2)))
        if key == self._shown:
            return
        self._shown = key
        pix = self.frames[self.anim][self.frame % len(self.frames[self.anim])]
        if self.zoom != 1.0:
            pix = pix.scaled(max(2, round(pix.width() * self.zoom)), max(2, round(pix.height() * self.zoom)),
                             Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if self.facing > 0:
            pix = pix.transformed(QTransform().scale(-1, 1))
        self._label.setPixmap(pix)
        self._label.resize(pix.size())
        self.resize(pix.size())

    def _advance(self, dt: float) -> None:
        self._anim_ms += dt * 1000
        if self._anim_ms >= ANIM_FRAME_MS:
            self._anim_ms = 0
            self.frame = (self.frame + 1) % len(self.frames[self.anim])

    def set_anim(self, name: str) -> None:
        if name != self.anim:
            self.anim, self.frame, self._anim_ms = name, 0, 0.0

    def set_zoom(self, zoom: float) -> None:
        """Resize around the centre (the fish shrinking into the bag)."""
        cx, cy = self.cx, self.cy
        self.zoom = zoom
        self._shown = (None, None, None)
        self._render()
        self.place_center(cx, cy)

    # --- the mouse ------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.mode == "free":
            self.mode = "dragged"
            self._grab = event.globalPos() - self.pos()
            self._trail = [(time.monotonic(), event.globalPos().x(), event.globalPos().y())]
            self.vx = self.vy = 0.0
            self.on_ground = False
            self.set_anim("attack")                  # it thrashes in the hand
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self.mode != "dragged":
            return
        area = get_total_screen_rect()
        target = event.globalPos() - self._grab
        self.x_pos = min(max(target.x(), area.left()), area.right() - self.width())
        self.y_pos = min(max(target.y(), area.top()), area.bottom() - self.height())
        self.move(int(self.x_pos), int(self.y_pos))
        now = time.monotonic()
        self._trail.append((now, event.globalPos().x(), event.globalPos().y()))
        self._trail = [pt for pt in self._trail if now - pt[0] <= THROW_WINDOW_S * 3]

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self.mode != "dragged":
            return
        now = time.monotonic()
        recent = [pt for pt in self._trail if now - pt[0] <= THROW_WINDOW_S]
        vx = vy = 0.0
        if len(recent) >= 2 and recent[-1][0] > recent[0][0]:
            span = recent[-1][0] - recent[0][0]
            vx, vy = (recent[-1][1] - recent[0][1]) / span, (recent[-1][2] - recent[0][2]) / span
        speed = (vx * vx + vy * vy) ** 0.5
        if speed > THROW_MAX:                        # a throw has a limit
            vx, vy = vx * THROW_MAX / speed, vy * THROW_MAX / speed
        self.mode = "free"
        self.vx, self.vy = vx, vy
        self.gravity = GRAVITY_FALL
        self.on_ground = False
        self.cooldown = LAND_COOLDOWN
        if abs(vx) > 40:
            self.facing = 1 if vx > 0 else -1
        self.setCursor(Qt.OpenHandCursor)

    def tick_dragged(self, dt: float) -> None:
        """Animate the fish while the mouse holds it."""
        self._advance(dt)
        self._render()

    # --- life ---------------------------------------------------------------

    def drop(self, x: float, top: float) -> None:
        """Start above the top of the screen and fall."""
        self.x_pos, self.y_pos = x, top - self.height()
        self.vx = self.vy = 0.0
        self.gravity = GRAVITY_FALL
        self.on_ground = False
        self.move(int(self.x_pos), int(self.y_pos))

    def _launch(self, travel: float, apex: float, seconds: float) -> None:
        """A jump that goes `travel` pixels sideways, reaches `apex` pixels high and lasts `seconds`."""
        self.gravity = 8 * apex / seconds ** 2
        self.vy = -4 * apex / seconds
        self.vx = travel / seconds
        self.on_ground = False
        self.facing = 1 if travel > 0 else -1

    def step(self, dt: float, prinny_cx, floor_line: float, area) -> None:
        """
        Move for `dt` seconds.

        Args:
            prinny_cx: horizontal centre of Prinny, or None when he is not around.
            floor_line: screen y of the ground (the bottom of the fish rests on it).
            area: QRect of the screen.
        """
        s = self.factor / FISH_SCALE          # distances follow Prinny's size setting
        floor_y = floor_line - self.height()
        if self.on_ground:
            self.cooldown = max(0.0, self.cooldown - dt)
            self.vx = 0.0
            moving = False
            if prinny_cx is not None:
                dx = self.cx - prinny_cx
                dist = abs(dx)
                away = 1 if dx > 0 else -1 if dx < 0 else self.rng.choice((-1, 1))
                cornered = (away > 0 and self.cx > area.right() - EDGE_MARGIN * s) or \
                           (away < 0 and self.cx < area.left() + EDGE_MARGIN * s)
                if dist < JUMP_RANGE * s and self.cooldown <= 0 and (cornered or self.rng.random() < JUMP_RATE * dt):
                    # over Prinny: to his other side, high enough to clear his head
                    self._launch(-away * (dist + OVER_DISTANCE * s), JUMP_APEX * s, JUMP_TIME)
                elif dist < FLEE_RANGE * s:
                    if self.cooldown <= 0 and self.rng.random() < HOP_RATE * dt:
                        self._launch(away * HOP_DISTANCE * s, HOP_APEX * s, HOP_TIME)
                    else:
                        self.vx = away * FLEE_SPEED * s
                        self.facing = away
                        moving = True
            if self.on_ground:
                self.set_anim("walk" if moving else "wait")
        else:
            self.vy += self.gravity * dt
            self.set_anim("jump")

        self.x_pos += self.vx * dt
        if not self.on_ground:
            self.y_pos += self.vy * dt
            if self.y_pos >= floor_y and self.vy > 0:
                self.y_pos, self.vy, self.vx = floor_y, 0.0, 0.0
                self.on_ground, self.cooldown = True, LAND_COOLDOWN
        else:
            self.y_pos = floor_y
        left, right = area.left(), area.right() - self.width()
        if self.x_pos < left or self.x_pos > right:
            self.x_pos = min(max(self.x_pos, left), right)
            self.vx = -self.vx * 0.3 if not self.on_ground else 0.0      # a thrown fish bounces off the side
            if self.vx:
                self.facing = 1 if self.vx > 0 else -1
        if self.y_pos < area.top():
            self.y_pos, self.vy = area.top(), abs(self.vy) * 0.3        # ... and off the top

        self._advance(dt)
        self._render()
        self.move(int(round(self.x_pos)), int(round(self.y_pos)))


class WorldMixin:
    """The fish and the hunt, for Prinny."""

    _fish_frames_base = None

    def _init_world(self) -> None:
        self._fish          = []
        self._catch         = None        # the catch in progress, see _start_catch
        self._hunting       = False
        self._fish_caught   = 0
        self._tip_cache     = {}
        self._dangle        = 0.0         # seconds a fish has been held over him
        self._crying        = False
        self._world_last    = time.monotonic()
        self._world_timer   = QTimer(self)
        self._world_timer.timeout.connect(self._world_tick)
        # flames over the eyes while a fish is on the desktop
        self._eyes_data     = None
        self._flame_frames  = {}                  # Prinny's size -> scaled flame images
        self._flame_tick    = 0
        self._flame_labels  = [QLabel(self), QLabel(self)]
        for label in self._flame_labels:
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            label.hide()
        self._flame_timer = QTimer(self)
        self._flame_timer.timeout.connect(self._update_flames)

    # --- placing --------------------------------------------------------------

    def _fish_frames(self) -> tuple:
        """The fish drawings, scaled to Prinny's size setting."""
        factor = FISH_SCALE * self._scale / 100
        if WorldMixin._fish_frames_base is None:
            WorldMixin._fish_frames_base = {
                anim: load_sprites(os.path.join("assets", "entities", "fish", anim)) for anim in FISH_ANIMATIONS}
        return {anim: [p.scaled(round(p.width() * factor), round(p.height() * factor),
                                Qt.KeepAspectRatio, Qt.SmoothTransformation) for p in frames]
                for anim, frames in WorldMixin._fish_frames_base.items()}, factor

    def spawn_fish(self, rng=None) -> tuple:
        """Drop a fish from the top of the screen, far from Prinny. Returns (done, what happened, for the chat)."""
        if len(self._fish) >= MAX_FISH:
            return False, "there are already enough fish on the desktop"
        frames, factor = self._fish_frames()
        if not frames["wait"]:
            return False, "the fish drawings are missing"
        fish = FishEntity(frames, factor, rng)
        area = get_total_screen_rect()
        px = self.x() + self.width() // 2
        # on the side of the screen that is farthest from Prinny
        far_left = px - area.left() > area.right() - px
        lo, hi = (area.left() + 40, px - 250) if far_left else (px + 250, area.right() - fish.width() - 40)
        if hi <= lo:
            lo, hi = area.left() + 40, area.right() - fish.width() - 40
        fish.drop(random.uniform(lo, max(lo, hi)) if rng is None else rng.uniform(lo, max(lo, hi)), area.top())
        fish.facing = random.choice((-1, 1)) if rng is None else rng.choice((-1, 1))
        fish.show()
        self._fish.append(fish)
        self._world_last = time.monotonic()
        self._world_timer.start(WORLD_INTERVAL_MS)
        self._flame_timer.start(FLAME_MS)
        return True, "a fish was dropped on the desktop: Prinny goes after it"

    # --- the loop -------------------------------------------------------------

    def _world_tick(self) -> None:
        now = time.monotonic()
        dt, self._world_last = min(0.1, now - self._world_last), now
        self._world_step(dt)

    def _on_ground(self, floor_line: float) -> bool:
        return not self._jumping and self.y() >= floor_line - self.height() - 3

    def _can_hunt(self) -> bool:
        return (self._forced_state is None and self._fight is None and not self._dragging and not self._menu_active
                and self._reaction_anim is None)

    def _world_step(self, dt: float) -> None:
        """One step of the world: the fish move, Prinny runs after the nearest one, and catches it if he can."""
        if not self._fish:
            self._world_timer.stop()
            self._stop_flames()
            return
        area = get_total_screen_rect()
        floor_line = area.bottom() - GROUND_OFFSET
        if self._silenced():                              # hidden or a full-screen app: the fish wait out of sight
            for f in self._fish:
                f.hide()
            self._hunting = False
            return
        for f in self._fish:
            if not f.isVisible():
                f.show()
        prinny_cx = self.x() + self.width() / 2
        self._cry_step(dt, prinny_cx)
        if self._catch:
            self._catch_step(dt)
        for f in self._fish:
            if f.mode == "free":
                f.step(dt, prinny_cx, floor_line, area)
            elif f.mode == "dragged":
                f.tick_dragged(dt)

        free = [f for f in self._fish if f.mode in ("free", "dragged")]
        if self._catch or not free:
            return
        if not self._can_hunt():
            if self._hunting:                              # an order or a drag took him away from the hunt
                self._hunting, self._goto_x, self._walk_active = False, None, False
            return
        if self._jumping or self._throw is not None or not self._on_ground(floor_line):
            return                                         # a jump started is finished on its course; he steers again once landed
        if self._bowl is not None:
            return                                         # the dish comes first: the meal takes him (see food.py)
        target = min(free, key=lambda f: abs(f.cx - prinny_cx))
        if not self._hunting:
            self._hunting = True
            self._reset_behaviour_flags()                  # stop whatever he was doing
        self._goto_x = int(min(max(target.cx - self.width() / 2, area.left()), area.right() - self.width()))
        self._goto_deadline = time.monotonic() + 2.0
        self._walk_active = True
        s = self._scale / 100
        if target.mode == "free" and target.on_ground and self._on_ground(floor_line) \
                and abs(target.cx - prinny_cx) < CATCH_DISTANCE * s:
            self._start_catch(target)

    # --- crying over a fish he cannot have --------------------------------------

    def _cry_step(self, dt: float, prinny_cx: float) -> None:
        """A fish held by the mouse over his head for too long makes him cry, until the fish is let go and moves again."""
        s = self._scale / 100
        held = [f for f in self._fish if f.mode == "dragged"]
        over = [f for f in held if abs(f.cx - prinny_cx) < CRY_RANGE * s and f.y_pos + f.height() <= self.y() + self.height() * 0.55]
        if self._crying:
            if self._reaction_anim != "cry":             # an order, a drag or a throw took him out of it
                self._crying = False
            elif not held:                               # the fish is free and runs: he moves again
                self._crying = False
                self._end_reaction()
            return
        if over and not self._catch and self._forced_state is None and not self._dragging and not self._menu_active:
            self._dangle += dt
            if self._dangle >= CRY_AFTER_S:
                self._dangle = 0.0
                self._crying = True
                self._hunting, self._goto_x, self._walk_active = False, None, False
                self._start_reaction("cry", None)
                self._show_bubble(t("world_fish_cry"), 5000)
        else:
            self._dangle = 0.0

    # --- the catch ------------------------------------------------------------

    def _start_catch(self, fish) -> None:
        fish.mode = "held"
        fish.set_zoom(1.0)
        fish.facing = -1 if self._direction < 0 else 1
        fish.set_anim("attack")
        fish.raise_()
        self._hunting, self._goto_x, self._walk_active = False, None, False
        self._catch = {"fish": fish, "phase": "hold", "t": 0.0, "from": (fish.cx, fish.cy)}
        self._start_reaction("hype", HOLD_MS)             # his raised hand holds the fish

    def _hand_point(self) -> tuple:
        """Screen position of the raised hand in the current 'hype' frame of the current skin."""
        frames = self._sprites.get("hype") or []
        if not frames:
            return self.x() + self.width() * 0.3, self.y() + self.height() * 0.3
        index = self._frame % len(frames)
        key = (self._current_skin, self._scale, index)
        pix = frames[index]
        if key not in self._tip_cache:
            img = pix.toImage()
            tip = None
            for y in range(img.height()):
                xs = [x for x in range(int(img.width() * HAND_FROM_SPRITE)) if img.pixelColor(x, y).alpha() > 40]
                if xs:
                    tip = (sum(xs) / len(xs), y + 2)
                    break
            self._tip_cache[key] = tip or (img.width() * 0.3, img.height() * 0.25)
        tx, ty = self._tip_cache[key]
        if self._direction == 1:                          # the sprite is mirrored when he faces right
            tx = pix.width() - tx
        return self.x() + tx, self.y() + ty

    def _bag_point(self) -> tuple:
        bx = BAG_REL[0] if self._direction != 1 else 1 - BAG_REL[0]
        return self.x() + self.width() * bx, self.y() + self.height() * BAG_REL[1]

    def _catch_step(self, dt: float) -> None:
        c = self._catch
        fish = c["fish"]
        c["t"] += dt * 1000
        if self._dragging:                                # picked up by the user: the catch ends here
            self._end_catch(stored=False)
            return
        if c["phase"] == "hold":
            hx, hy = self._hand_point()
            fish.facing = 1 if self._direction == 1 else -1
            fish.place_center(hx, hy - fish.height() * 0.30)
            fish._advance(dt)
            fish._render()
            fish.raise_()
            if c["t"] >= HOLD_MS:
                c.update(phase="store", t=0.0, **{"from": (fish.cx, fish.cy)})
                self._start_reaction("eat", KEEP_MS)      # he eats it (skins with big accessories keep busy with the bag instead)
        elif c["phase"] == "store":
            k = min(1.0, c["t"] / STORE_MS)
            bx, by = self._bag_point()
            sx, sy = c["from"]
            arc = -40 * (1 - abs(2 * k - 1))              # a little hop on the way
            fish.mode = "storing"
            fish.set_zoom(max(0.15, 1.0 - 0.85 * k))
            fish.place_center(sx + (bx - sx) * k, sy + (by - sy) * k + arc)
            if k >= 1.0:
                self._end_catch(stored=True)

    def _end_catch(self, stored: bool) -> None:
        fish = self._catch["fish"]
        self._catch = None
        fish.hide()
        fish.close()
        if fish in self._fish:
            self._fish.remove(fish)
        if stored:
            self._fish_caught += 1
            self._show_bubble(t("world_fish_stored"), 4000)
        if not self._fish:
            self._world_timer.stop()
            self._stop_flames()

    # --- the flames in his eyes ------------------------------------------------

    def _eyes(self) -> dict:
        """{skin: {animation: [[(x, y), ...] per frame]}}, from assets/sprites/eyes.json."""
        if self._eyes_data is None:
            try:
                with open(resource_path(os.path.join("assets", "sprites", "eyes.json")), encoding="utf-8") as f:
                    self._eyes_data = json.load(f)
            except (OSError, ValueError):
                self._eyes_data = {}
        return self._eyes_data

    def _flames(self) -> list:
        """The flame images for the current size setting."""
        if self._scale not in self._flame_frames:
            base = [QPixmap(resource_path(os.path.join("assets", "entities", "flames", f"{n}.png"))) for n in range(1, 7)]
            k = FLAME_WIDTH_PX * self._scale / 100 / FLAME_CONTENT_W
            self._flame_frames[self._scale] = [
                p.scaled(round(p.width() * k), round(p.height() * k), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                for p in base if not p.isNull()]
        return self._flame_frames[self._scale]

    def _flames_follow(self) -> None:
        """Called by Prinny each time his picture changes: the flames move to the eyes of the new picture."""
        if self._fish:
            self._update_flames(advance=False)

    def _stop_flames(self) -> None:
        self._flame_timer.stop()
        for label in self._flame_labels:
            label.hide()

    def _update_flames(self, advance: bool = True) -> None:
        """
        Put a flame on each eye that shows in the current frame, while at least one fish is on the desktop.

        Args:
            advance: go to the next flame image (the flame timer); False when Prinny just changed frame and the flames
                only have to follow his eyes.
        """
        eyes = []
        if self._fish and not self._silenced() and self._current_anim in FLAME_ANIMATIONS:
            per_frame = self._eyes().get(self._current_skin, {}).get(self._current_anim)
            frames = self._sprites.get(self._current_anim) or []
            if per_frame and frames:
                eyes = per_frame[self._frame % len(per_frame)]
        flames = self._flames()
        if not eyes or not flames:
            for label in self._flame_labels:
                label.hide()
            return
        scale = self._scale / 100
        pix = self._sprites[self._current_anim][self._frame % len(self._sprites[self._current_anim])]
        flipped = self._direction == 1                       # the sprite is mirrored when he faces right
        if advance:
            self._flame_tick += 1
        k = FLAME_WIDTH_PX * scale / FLAME_CONTENT_W
        for i, label in enumerate(self._flame_labels):
            if i >= len(eyes):
                label.hide()
                continue
            ex, ey = eyes[i][0] * scale, eyes[i][1] * scale
            if flipped:
                ex = pix.width() - ex
            image = flames[(self._flame_tick + 2 * i) % len(flames)]
            label.setPixmap(image)
            label.resize(image.size())
            label.move(int(ex - FLAME_BASE[0] * k), int(ey + FLAME_DROP * scale - FLAME_BASE[1] * k))
            label.show()
            label.raise_()
