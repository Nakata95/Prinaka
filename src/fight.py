"""
fight.py
--------
A staged fight between Prinny and an opponent that drops onto the desktop (the Rabbit or the Pumpkin).

Nothing is simulated: the fight is a script, a chain of random "beats" in the style of a manga duel (both strike at the
same moment and are thrown back, one dodges by jumping over the other, one is hit and sent flying...), followed by a
finale where one of them wins. Both fighters are moved by a single timer so that they stay in step; Prinny's own
behaviour is paused while it runs (see Prinny._update) and resumes when it ends.

FightMixin is mixed into the Prinny widget. Everything is in memory: nothing is saved.
"""

import math
import os
import random
import time

from PyQt5.QtWidgets import QLabel, QWidget
from PyQt5.QtCore import Qt, QTimer, QPointF
from PyQt5.QtGui import QPainter, QPixmap, QPolygonF, QColor, QTransform

from utils import get_total_screen_rect, load_sprites, t


# ---------------------------------------------------------------------------
# Constants (pixels at Prinny's 100% size, seconds)
# ---------------------------------------------------------------------------

FIGHT_INTERVAL_MS = 30
TEMPO             = 1.7         # the fight runs this much faster than real time (speeds, jumps and pauses alike)
GROUND_OFFSET     = 40          # same as Prinny: pixels above the bottom of the screen
# the opponents: folder of their drawings, size relative to Prinny's size setting, and their lines of dialogue
OPPONENTS         = {"rabbit": 0.88, "pumpkin": 1.12, "bat": 1.2, "wrestler": 1.0}
BAT_ANIMS         = ("fly", "fly2", "hit", "die")
BAT_COUNT         = 3
BAT_WINS          = 0.2         # chance that the swarm gets the better of him in the end
BAT_FRAME_S       = 0.07        # wing beat
RABBIT_ANIMS      = ("stand", "wait", "walk", "attack", "damage", "jump", "lift", "magic", "squat")
WRESTLER_ANIMS    = RABBIT_ANIMS + ("tumble", "pose")
ANIM_FRAME_S      = 0.11

GRAVITY           = 2300.0
RUN               = 190.0       # both run at about this speed when they charge
GUARD_DISTANCE    = 230         # distance between them when they face each other
REACH             = 95          # distance at which a strike lands
BEATS             = (6, 9)      # how many exchanges before the finale
RABBIT_WINS       = 0.5         # chance that the rabbit wins in the end
CLASH_LOCK       = 0.5         # chance that a clash turns into a struggle
LOCK_SECONDS      = (1.4, 2.4)  # how long they push against each other
BOUNCE            = 0.45        # speed kept after hitting the side of the screen
FLASH_S           = 0.28

BEAT_NAMES = ("clash", "prinny_dodged", "rabbit_dodged", "prinny_hit", "rabbit_hit", "crossing", "taunt")


class RabbitWidget(QWidget):
    """The opponent's window: a label showing the current frame, click-through."""

    def __init__(self, frames: dict):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.frames = frames
        self._label = QLabel(self)
        first = next(f for f in frames.values() if f)[0]
        self.resize(first.width(), first.height())
        self._label.resize(self.size())
        self._shown = None

    def draw(self, anim: str, frame: int, facing: int) -> None:
        key = (anim, frame, facing)
        if key == self._shown:
            return
        self._shown = key
        pix = self.frames[anim][frame % len(self.frames[anim])]
        if facing > 0:
            pix = pix.transformed(QTransform().scale(-1, 1))
        # frames can differ in size: they are drawn bottom-centre in the window
        canvas = QPixmap(self.size())
        canvas.fill(Qt.transparent)
        p = QPainter(canvas)
        p.drawPixmap((self.width() - pix.width()) // 2, self.height() - pix.height(), pix)
        p.end()
        self._label.setPixmap(canvas)


class Flash(QWidget):
    """A comic-book star burst that appears for a moment where two blows meet."""

    def __init__(self, size: int):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.resize(size, size)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c, n = self.width() / 2, 10
        points = []
        for i in range(n * 2):
            radius = (0.5 if i % 2 == 0 else 0.24) * self.width() * (1.0 if i % 4 else 0.85)
            angle = math.pi * i / n
            points.append(QPointF(c + radius * math.cos(angle), c + radius * math.sin(angle)))
        p.setPen(QColor(120, 40, 20))
        p.setBrush(QColor(255, 236, 120))
        p.drawPolygon(QPolygonF(points))
        p.setBrush(QColor(255, 255, 255))
        p.setPen(Qt.NoPen)
        inner = [QPointF(c + (pt.x() - c) * 0.45, c + (pt.y() - c) * 0.45) for pt in points]
        p.drawPolygon(QPolygonF(inner))


class Fighter:
    """
    One of the two fighters: a position on the ground, a height above it and a speed, with a pose.

    cx is the horizontal centre, h the height above the ground (up is positive). `apply` writes the result to the
    window (Prinny's or the rabbit's). A fighter in the air falls by gravity; one that was thrown also slides on landing.
    """

    def __init__(self, name: str, width: float, apply, pose):
        self.name, self.width, self._apply, self._pose = name, width, apply, pose
        self.cx = 0.0
        self.h = 0.0
        self.vx = 0.0
        self.vh = 0.0
        self.facing = -1
        self.anim = "idle"
        self.thrown = False         # bounces off the sides while flying, then slides
        self.visible = True
        self.fly = False            # flies: no gravity, it hovers at base_h and bobs
        self.base_h = 0.0
        self.bob = 0.0
        self.phase = 0.0
        self.alive = True
        self.dying = 0.0            # seconds since it landed after being killed
        self.widget = None
        self.style = "fly"

    @property
    def air(self) -> bool:
        return self.h > 0 or self.vh > 0

    def launch(self, vx: float, vh: float, anim: str | None = None, thrown: bool = False) -> None:
        self.vx, self.vh, self.thrown = vx, vh, thrown
        self.h = max(self.h, 0.01)
        if anim:
            self.anim = anim

    def step(self, dt: float, left: float, right: float) -> None:
        if self.fly:
            self.h = max(0.0, self.base_h + self.bob * math.sin(self.clock * 5 + self.phase))
            self.cx += self.vx * dt
            lo, hi = left + self.width / 2, right - self.width / 2
            self.cx = min(max(self.cx, lo), hi)
            return
        if self.air:
            self.vh -= GRAVITY * self._k * dt
            self.h += self.vh * dt
            self.cx += self.vx * dt
            if self.h <= 0:
                self.h, self.vh = 0.0, 0.0
                if not self.thrown:
                    self.vx = 0.0
        elif self.thrown:                                   # sliding after a throw
            self.cx += self.vx * dt
            self.vx *= max(0.0, 1.0 - 7.0 * dt)
            if abs(self.vx) < 12:
                self.vx, self.thrown = 0.0, False
        lo, hi = left + self.width / 2, right - self.width / 2
        if self.cx < lo:
            self.cx, self.vx = lo, (abs(self.vx) * BOUNCE if self.thrown else 0.0)
        elif self.cx > hi:
            self.cx, self.vx = hi, (-abs(self.vx) * BOUNCE if self.thrown else 0.0)

    bounds = None
    _k = 1.0                                                # gravity scale, set with the size of the fighters

    def show_pose(self) -> None:
        if self.bounds:                                     # what the script moved by hand stays on the screen
            self.cx = min(max(self.cx, self.bounds[0] + self.width / 2), self.bounds[1] - self.width / 2)
        self._pose(self)
        self._apply(self)


class FightMixin:
    """Prinny's side of the fight: starting it, the timeline of beats and putting everything back."""

    _rabbit_frames_base = None

    def _init_fight(self) -> None:
        self._fight        = None          # the running Fight, or None
        self._fight_timer  = QTimer(self)
        self._fight_timer.timeout.connect(self._fight_tick)

    # --- starting -------------------------------------------------------------

    def _rabbit_pixmaps(self, kind: str = "rabbit") -> dict:
        if FightMixin._rabbit_frames_base is None:
            FightMixin._rabbit_frames_base = {}
        if kind not in FightMixin._rabbit_frames_base:
            FightMixin._rabbit_frames_base[kind] = {
                anim: load_sprites(os.path.join("assets", "entities", kind, anim))
                for anim in {"bat": BAT_ANIMS, "wrestler": WRESTLER_ANIMS}.get(kind, RABBIT_ANIMS)}
        factor = OPPONENTS[kind] * self._scale / 100
        return {anim: [p.scaled(round(p.width() * factor), round(p.height() * factor),
                                Qt.KeepAspectRatio, Qt.SmoothTransformation) for p in frames]
                for anim, frames in FightMixin._rabbit_frames_base[kind].items()}

    def _can_fight(self) -> bool:
        area = get_total_screen_rect()
        ground_y = area.bottom() - self.height() - GROUND_OFFSET
        return (self._fight is None and not self._dragging and self._throw is None
                and not self._jumping and not self._catch and self.y() >= ground_y - 3 and not self._silenced())

    def spawn_rabbit(self, rng=None) -> tuple:
        return self.spawn_opponent("rabbit", rng)

    def spawn_pumpkin(self, rng=None) -> tuple:
        return self.spawn_opponent("pumpkin", rng)

    def spawn_opponent(self, kind: str = "rabbit", rng=None) -> tuple:
        """An opponent drops in and the fight starts. Returns (done, what happened, for the chat)."""
        if self._fight is not None:
            return False, "a fight is already going on"
        if not self._can_fight():
            return False, "Prinny cannot fight right now"
        frames = self._rabbit_pixmaps(kind)
        if not frames["fly" if kind == "bat" else "wait"]:
            return False, f"the {kind} drawings are missing"
        rng = rng or random
        s = self._scale / 100
        area = get_total_screen_rect()
        k = s
        px = self.x() + self.width() / 2
        # the opponent drops in on the side of the screen with the most room
        room_left, room_right = px - area.left(), area.right() - px
        side = 1 if room_right >= room_left else -1
        dist = rng.uniform(GUARD_DISTANCE * 1.4, GUARD_DISTANCE * 2.2) * s
        floor_line = area.bottom() - GROUND_OFFSET
        swarm = kind == "bat"

        def make(name):
            widget = RabbitWidget(frames)

            def apply(f):
                widget.move(int(round(f.cx - widget.width() / 2)), int(round(floor_line - widget.height() - f.h)))

            def pose(f):
                n = len(frames[f.anim])
                if swarm:
                    if f.anim in ("fly", "fly2"):
                        idx = int(f.clock / BAT_FRAME_S) % n
                    else:
                        idx = min(int(f.clock / 0.12), n - 1)
                else:
                    idx = int(f.clock / ANIM_FRAME_S) if f.anim in ("walk", "wait", "attack", "magic", "lift", "tumble", "pose", "jump", "squat") else 0
                    if f.anim == "attack":
                        idx = min(idx, n - 1)
                widget.draw(f.anim, idx, f.facing)

            f = Fighter(name, widget.width(), apply, pose)
            f.clock, f._k, f.widget = 0.0, 1.0, widget
            return f

        def prinny_apply(f):
            self.move(int(round(f.cx - self.width() / 2)), int(round(area.bottom() - self.height() - GROUND_OFFSET - f.h)))

        def prinny_pose(f):
            self._direction = f.facing
            self._set_anim(f.anim)

        p = Fighter("prinny", self.width(), prinny_apply, prinny_pose)
        p.clock, p._k = 0.0, 1.0
        p.cx = px
        p.facing = side
        p.anim = "idle"
        if swarm:
            foes = [make(f"bat{i}") for i in range(BAT_COUNT)]
            for i, f in enumerate(foes):
                f.fly, f.style = True, ("fly" if i % 2 == 0 else "fly2")
                f.anim, f.bob, f.phase = f.style, 14 * s, rng.uniform(0, 6.28)
                f.cx = min(max(px + (i - 1) * 190 * s + side * 120 * s, area.left() + 60), area.right() - 60)
                f.base_h = area.height() * 1.05            # above the top of the screen: they swoop in
                f.facing = -side
            r = foes[0]
        else:
            r = make("rabbit")
            foes = [r]
            r.cx = min(max(px + side * dist, area.left() + r.width / 2), area.right() - r.width / 2)
            r.facing = -side
            r.h = area.height() * 0.8
            r.anim = "jump"
        self._reset_behaviour_flags()
        self._end_reaction()
        self._hunting = False
        self._fight = {"kind": kind, "p": p, "r": r, "foes": foes, "all": [p] + foes, "widget": r.widget,
                       "flash": Flash(round(120 * s)), "rng": rng, "s": s,
                       "area": area, "dt": FIGHT_INTERVAL_MS / 1000, "script": None, "wait": 0.0,
                       "last": time.monotonic(), "k": k}
        self._fight["script"] = self._swarm_script() if swarm else self._fight_script()
        for f in foes:
            f.show_pose()
            f.widget.show()
        self._fight_timer.start(FIGHT_INTERVAL_MS)
        return True, f"the {kind.capitalize()} dropped onto the desktop and a fight is about to start"

    # --- the loop -------------------------------------------------------------

    def _fight_tick(self) -> None:
        fight = self._fight
        if fight is None:
            self._fight_timer.stop()
            return
        if self._dragging or self._silenced():                       # the user took him, or a full-screen app
            self._end_fight(aborted=True)
            return
        now = time.monotonic()
        dt, fight["last"] = min(0.1, now - fight["last"]) * TEMPO, now
        fight["dt"] = dt
        area = fight["area"]
        left, right = area.left(), area.right()
        for f in fight["all"]:
            f.clock += dt
            f.bounds = (left, right)
            f.step(dt, left, right)
            if not f.alive and f.anim == "hit" and f.clock > 0.15 and f.widget is not None:
                f.anim, f.clock = "die", 0.0                          # the pieces scatter as it falls
            if f.dying >= 0 and not f.alive:                       # a killed bat: it lies where it fell, then it is gone
                if not f.air and not f.thrown:
                    f.dying += dt
                    if f.dying > 0.7 and f.widget.isVisible():
                        f.widget.hide()
        fight["wait"] -= dt
        while fight["wait"] <= 0 and fight["script"] is not None:
            try:
                value = next(fight["script"])
            except StopIteration:
                fight["script"] = None
                break
            fight["wait"] = float(value or 0)
            if fight["wait"] <= 0:
                break
        for f in fight["all"]:
            f.show_pose()
        if fight["flash"].isVisible() and now > fight.get("flash_until", 0):
            fight["flash"].hide()
        if fight["script"] is None:
            self._end_fight()

    def _end_fight(self, aborted: bool = False) -> None:
        fight, self._fight = self._fight, None
        self._fight_timer.stop()
        if fight is None:
            return
        for f in fight["foes"]:
            f.widget.hide()
            f.widget.deleteLater()
        fight["flash"].hide()
        fight["flash"].deleteLater()
        area = get_total_screen_rect()
        self.move(self.x(), area.bottom() - self.height() - GROUND_OFFSET)
        self._vy = 0
        self._direction = fight["p"].facing
        self._set_anim("idle")
        self._reset_behaviour_flags()

    # --- the choreography -------------------------------------------------------

    def _fight_script(self):
        """The whole fight, as a generator: it yields how long to wait (0 = the next tick)."""
        F = self._fight
        p, r, rng, s = F["p"], F["r"], F["rng"], F["s"]
        guard, reach = GUARD_DISTANCE * s, REACH * s
        run = RUN * s

        def sign(v):
            return 1 if v >= 0 else -1

        def face_off():
            p.facing = sign(r.cx - p.cx)
            r.facing = -p.facing

        def until(cond, limit=6.0):
            t0 = time.monotonic()
            while not cond() and time.monotonic() - t0 < limit:
                yield 0

        def landed(*fs):
            return lambda: all(not f.air and not f.thrown for f in fs)

        def settle(*fs):
            yield from until(landed(*fs))

        def charge(fighter, other, target_gap, speed, anim="walk"):
            """Run at the other until target_gap away."""
            fighter.anim = anim
            t0 = time.monotonic()
            while abs(other.cx - fighter.cx) > target_gap and time.monotonic() - t0 < 3.0:
                fighter.facing = sign(other.cx - fighter.cx)
                step = speed * F["dt"]
                fighter.cx += fighter.facing * min(step, abs(other.cx - fighter.cx) - target_gap)
                yield 0

        def walk_apart(target_gap):
            """Both walk (back) to the guard distance."""
            p.anim = r.anim = "walk"
            t0 = time.monotonic()
            while abs(abs(r.cx - p.cx) - target_gap) > 6 and time.monotonic() - t0 < 3.0:
                d = sign(r.cx - p.cx)
                move = (run * 0.6 * F["dt"]) * (1 if abs(r.cx - p.cx) > target_gap else -1)
                p.facing, r.facing = d, -d
                p.cx += d * move / 2
                r.cx -= d * move / 2
                yield 0
            p.anim, r.anim = "idle", "wait"

        def hop(fighter, dx, apex, anim):
            """A jump that lands dx further, apex pixels high."""
            vh = math.sqrt(2 * GRAVITY * apex * s)
            air_time = 2 * vh / GRAVITY
            fighter.launch(dx / air_time, vh, anim)

        def burst(x, y):
            F["flash"].move(int(x - F["flash"].width() / 2), int(y - F["flash"].height() / 2))
            F["flash"].show()
            F["flash_until"] = time.monotonic() + FLASH_S

        def impact_point():
            area = F["area"]
            return (p.cx + r.cx) / 2, area.bottom() - GROUND_OFFSET - 70 * s

        def prinny_lunge():
            """He runs in and strikes."""
            yield from charge(p, r, reach, run * 1.1)
            p.anim = "attack"

        def rabbit_lunge():
            yield from charge(r, p, reach, run * 1.15)
            r.anim = "attack"

        def knock_back(victim, direction, power, anim):
            victim.launch(direction * power * s, 330 * s * (1 + power / 900), anim, thrown=True)

        def vanish():
            for _ in range(6):                                              # it vanishes, blinking
                F["widget"].setVisible(not F["widget"].isVisible())
                yield 0.1
            F["widget"].hide()

        def slam(d, big=False):
            """The wrestler's finisher: he throws Prinny up, jumps over him, stands on him and crushes him into the ground;
            Prinny is sent flying by the impact."""
            ground = F["area"].bottom() - GROUND_OFFSET
            p0, r0 = p.cx, r.cx
            stand = 110 * s                                     # a standing wrestler's feet on Prinny's head
            top = min(380 * s, F["area"].height() - GROUND_OFFSET - stand - r.widget.height() - 10)   # stays on the screen
            p.fly = r.fly = True
            p.bob = r.bob = 0.0
            p.vx = r.vx = 0.0
            p.base_h = 0.01
            p.anim, r.anim, r.facing = "shock", "squat", d
            t = 0.0
            while t < 1.0:                                       # Prinny shoots up, the wrestler crouches then follows
                t += F["dt"] / 0.5
                e = min(1.0, t)
                p.base_h = top * (1 - (1 - e) ** 2)
                p.cx = p0 + d * 30 * s * e
                if e > 0.2:
                    k = (e - 0.2) / 0.8
                    ek = 1 - (1 - k) ** 2
                    r.anim = "jump"
                    r.base_h = (top + stand) * ek
                    r.cx = r0 + (p.cx - r0) * ek
                yield 0
            r.anim = "pose"                                      # standing on him at the top
            r.clock = 0.0
            p.anim = "shock"
            t = 0.0
            while t < 1.0:
                t += F["dt"] / 0.3
                r.base_h = p.base_h + stand
                r.cx = p.cx
                yield 0
            burst(p.cx, ground - top - 40 * s)
            t = 0.0
            while t < 1.0:                                       # both crash down
                t += F["dt"] / 0.3
                e = min(1.0, t) ** 2
                p.base_h = top * (1 - e)
                r.base_h = p.base_h + stand
                yield 0
            burst(p.cx, ground - 50 * s)
            p.fly = r.fly = False
            p.h, r.h = 0.01, 0.0
            r.anim = "squat"
            r.clock = 0.0
            p.launch(d * (950 if big else 780) * s, 560 * s, "shock", thrown=True)    # the impact throws him
            yield 0.12
            burst(p.cx, ground - 90 * s)

        def hit_p(d, power):
            """Prinny is hit: thrown back, or crushed by the wrestler's finisher."""
            if F["kind"] == "wrestler":
                yield from slam(d, power > 800)
            else:
                knock_back(p, d, power, "shock")
                if False:
                    yield 0

        # ---- the beats
        def clash():
            face_off()
            p.anim, r.anim = "walk", "walk"
            t0 = time.monotonic()
            while abs(r.cx - p.cx) > reach * 1.1 and time.monotonic() - t0 < 3.0:
                d = sign(r.cx - p.cx)
                step = run * F["dt"] * 0.9
                p.cx += d * step
                r.cx -= d * step
                yield 0
            p.anim = r.anim = "attack"
            p.clock = r.clock = 0.0
            yield 0.32
            burst(*impact_point())
            d = sign(r.cx - p.cx)
            power = 380
            if rng.random() < CLASH_LOCK:
                # neither gives way: face to face they spam their blows, the star bursting again and again, until the shock
                p0, r0 = p.cx, r.cx
                t_end = time.monotonic() + rng.uniform(*LOCK_SECONDS)
                n = 0
                while time.monotonic() < t_end:
                    n += 1
                    self._frame = 0                                    # Prinny starts his blow again
                    r.clock = 0.0
                    shake = (1 if n % 2 else -1) * 5 * s
                    p.cx, r.cx = p0 + shake - d * n * 0.6 * s, r0 + shake + d * n * 0.6 * s
                    if n % 2 == 0:
                        burst(*impact_point())
                    yield 0.1
                power = 620
            knock_back(p, -d, power, "shock")
            knock_back(r, d, power, "damage")
            yield from settle(p, r)
            yield 0.3

        def prinny_dodged():
            face_off()
            d = sign(r.cx - p.cx)
            yield from charge(p, r, reach * 1.7, run * 1.1)
            p.anim, r.anim = "attack", "jump"
            p.clock = 0.0
            hop(r, -d * (reach * 1.7 + reach * 0.9), 230, "jump")       # over him, landing behind
            r.facing = -d
            yield 0.45
            p.anim = "shrug"
            yield from settle(r)
            r.facing = d                                                 # it lands behind him and turns
            p.facing = -d                                                # he turns round to find it again
            r.anim = "wait"
            yield 0.6

        def rabbit_dodged():
            face_off()
            d = sign(p.cx - r.cx)
            yield from charge(r, p, reach * 1.7, run * 1.15)
            r.anim, p.anim = "attack", "fall"
            r.clock = 0.0
            hop(p, -d * (reach * 1.7 + reach * 0.9), 260, "fall")
            p.facing = -d
            yield 0.45
            r.anim = "squat"
            yield from settle(p)
            p.facing = d
            r.facing = -d
            p.anim = "grimace"
            yield 0.8

        def prinny_hit():
            face_off()
            d = sign(r.cx - p.cx)
            yield from prinny_lunge()
            yield 0.3
            burst(r.cx - d * 20 * s, F["area"].bottom() - GROUND_OFFSET - 80 * s)
            knock_back(r, d, 620, "damage")
            yield from settle(r)
            p.anim = "idle"
            r.anim = "squat"
            yield 0.7
            face_off()
            r.anim = "wait"
            yield from walk_apart(guard)

        def rabbit_hit():
            face_off()
            d = sign(p.cx - r.cx)
            yield from rabbit_lunge()
            yield 0.3
            burst(p.cx - d * 20 * s, F["area"].bottom() - GROUND_OFFSET - 80 * s)
            yield from hit_p(d, 620)
            yield from settle(p)
            r.anim = "wait"
            p.anim = "fail"
            yield 0.9
            p.anim = "idle"
            face_off()
            yield from walk_apart(guard)

        def crossing():
            """Both jump at each other and pass in mid-air, then land back to back and turn."""
            face_off()
            d = sign(r.cx - p.cx)
            gap = abs(r.cx - p.cx)
            p.anim, r.anim = "fall", "jump"
            hop(p, d * gap, 250, "fall")
            hop(r, -d * gap, 190, "jump")
            yield from settle(p, r)
            p.facing, r.facing = d, -d                                   # back to back
            yield 0.35
            face_off()
            p.anim, r.anim = "idle", "wait"
            yield from walk_apart(guard)

        def taunt():
            face_off()
            r.anim = rng.choice(("lift", "magic"))
            r.clock = 0.0
            yield 0.9
            p.anim = "grimace"
            yield 0.9
            r.anim, p.anim = "wait", "idle"
            yield 0.3

        # ---- the opening: the rabbit lands, they size each other up
        yield from until(lambda: not r.air, 4.0)
        face_off()
        r.anim = "squat"
        yield 0.35
        r.anim = "wait"
        p.anim = "grimace"
        self._show_bubble(t("fight_start_" + F["kind"]), 3500)
        yield 0.8
        p.anim = "idle"
        yield from walk_apart(guard)
        yield 0.4

        # ---- the exchanges
        table = {"clash": clash, "prinny_dodged": prinny_dodged, "rabbit_dodged": rabbit_dodged,
                 "prinny_hit": prinny_hit, "rabbit_hit": rabbit_hit, "crossing": crossing, "taunt": taunt}
        last = None
        for _ in range(rng.randint(*BEATS)):
            name = rng.choice([n for n in BEAT_NAMES if n != last])
            last = name
            F["beat"] = name
            yield from table[name]()
            yield 0.2

        # ---- the finale
        face_off()
        rabbit_wins = rng.random() < RABBIT_WINS
        F["rabbit_wins"] = rabbit_wins
        if rabbit_wins:
            d = sign(p.cx - r.cx)
            yield from rabbit_lunge()
            yield 0.3
            burst(p.cx - d * 20 * s, F["area"].bottom() - GROUND_OFFSET - 80 * s)
            yield from hit_p(d, 1000)
            yield from settle(p)
            p.anim = "cry"
            r.anim = "magic"
            r.clock = 0.0
            r.facing = d
            self._show_bubble(t("fight_lose_" + F["kind"]), 4000)
            yield 2.6
            r.anim = "walk"
            r.facing = -d
            for _ in range(int(1.2 / (F["dt"]))):         # it walks off
                r.cx += -d * run * 1.3 * F["dt"]
                yield 0
            yield from vanish()
        else:
            d = sign(r.cx - p.cx)
            yield from prinny_lunge()
            yield 0.3
            burst(r.cx - d * 20 * s, F["area"].bottom() - GROUND_OFFSET - 80 * s)
            knock_back(r, d, 1000, "damage")
            yield from settle(r)
            p.anim = "idle"
            yield 0.5
            yield from vanish()
            p.facing = -d
            p.anim = "hype"
            p.clock = 0.0
            self._show_bubble(t("fight_win"), 4000)
            yield 2.4
        p.anim = "idle"
        yield 0.2

    # --- the swarm: one against three --------------------------------------------

    def _swarm_script(self):
        """Prinny against three fragile bats: dives, dodges, a spin that cuts through them, a finale."""
        F = self._fight
        p, bats, rng, s = F["p"], F["foes"], F["rng"], F["s"]
        area = F["area"]
        state = {"kills": 0, "beats": 0}
        bats_win = rng.random() < BAT_WINS

        def sign(v):
            return 1 if v >= 0 else -1

        def alive():
            return [b for b in bats if b.alive]

        def until(cond, limit=6.0):
            t0 = time.monotonic()
            while not cond() and time.monotonic() - t0 < limit:
                yield 0

        def settle(*fs):
            yield from until(lambda: all(not f.air and not f.thrown for f in fs))

        def inside(x):
            return min(max(x, area.left() + 70 * s), area.right() - 70 * s)

        def burst(x, y):
            F["flash"].move(int(x - F["flash"].width() / 2), int(y - F["flash"].height() / 2))
            F["flash"].show()
            F["flash_until"] = time.monotonic() + FLASH_S

        def burst_at(b):
            burst(b.cx, area.bottom() - GROUND_OFFSET - b.h - 30 * s)

        def look(b=None):
            targets = alive()
            if targets:
                b = b or min(targets, key=lambda x: abs(x.cx - p.cx))
                p.facing = sign(b.cx - p.cx)

        def glide(moves, dur):
            """moves: [(bat, x, h)]: they all fly to their spot in dur seconds."""
            starts = [(b, b.cx, b.base_h, x, h) for b, x, h in moves]
            for b, sx, _sh, x, _h in starts:
                if abs(x - sx) > 8:
                    b.facing = sign(x - sx)
            t = 0.0
            while t < 1.0:
                t += F["dt"] / dur
                e = min(1.0, t)
                e = e * e * (3 - 2 * e)
                for b, sx, sh, x, h in starts:
                    b.cx, b.base_h = sx + (x - sx) * e, sh + (h - sh) * e
                yield 0

        def hover_spots():
            """Where the living bats wait: spread around Prinny, above his head."""
            live = alive()
            xs = [-270, 0, 270] if len(live) == 3 else ([-200, 200] if len(live) == 2 else [rng.choice((-220, 220))])
            rng.shuffle(xs)
            return [(b, inside(p.cx + x * s + rng.uniform(-40, 40) * s), rng.uniform(190, 280) * s)
                    for b, x in zip(live, xs)]

        def regroup(dur=0.5):
            for b in alive():
                b.anim = b.style
            yield from glide(hover_spots(), dur)

        def hop(fighter, dx, apex, anim):
            vh = math.sqrt(2 * GRAVITY * apex * s)
            fighter.launch(dx / (2 * vh / GRAVITY), vh, anim)
            return vh / GRAVITY                                         # time to the top

        def knock_back(victim, direction, power, anim):
            victim.launch(direction * power * s, 330 * s * (1 + power / 900), anim, thrown=True)

        def kill(b, direction):
            """The bat bursts into pieces and falls."""
            burst_at(b)
            b.alive = False
            b.fly = False
            b.anim, b.clock = "hit", 0.0
            b.dying = 0.0
            b.launch(direction * 230 * s, 200 * s, "hit", thrown=True)
            state["kills"] += 1

        def may_kill():
            if state["beats"] < 3:                                       # first they dance around him
                return False
            if bats_win:
                return state["kills"] < 1 and len(alive()) > 2
            return len(alive()) > 1 and rng.random() < 0.5

        def pull_away(b, direction):
            return (b, inside(b.cx + direction * 250 * s), 300 * s)

        # ---- beats
        def dive_dodge():
            b = rng.choice(alive())
            side = sign(b.cx - p.cx)
            look(b)
            yield from glide([(b, inside(p.cx + side * 120 * s), 290 * s)], 0.3)
            b.anim = b.style
            hop(p, -side * 150 * s, 120, "fall")                          # he hops away as it dives
            yield from glide([(b, p.cx - side * 20 * s, 35 * s)], 0.28)
            yield from glide([(b, inside(p.cx - side * 260 * s), 230 * s)], 0.4)
            yield from settle(p)
            p.facing = sign(b.cx - p.cx)
            p.anim = "shrug"
            yield 0.35
            p.anim = "idle"

        def dive_slash():
            b = rng.choice(alive())
            side = sign(b.cx - p.cx)
            look(b)
            yield from glide([(b, inside(p.cx + side * 150 * s), 260 * s)], 0.3)
            top = hop(p, side * 40 * s, 170, "attack")                    # he jumps to meet it
            p.clock = 0.0
            yield from glide([(b, p.cx + side * 45 * s, 150 * s)], max(0.2, top * 0.9))
            if may_kill():
                kill(b, side)
                yield from settle(p)
            else:
                b.anim = b.style
                yield from glide([pull_away(b, side)], 0.3)                # it twists away from the blade
                yield from settle(p)
                p.anim = "grimace"
                yield 0.3
            p.anim = "idle"

        def swarm_rush():
            live = alive()
            look()
            moves = []
            for i, b in enumerate(live):
                side = -1 if i % 2 == 0 else 1
                moves.append((b, inside(p.cx + side * 250 * s + (i - 1) * 40 * s), 280 * s))
            yield from glide(moves, 0.35)
            top = hop(p, 0, 175, "attack")                                # a spin straight up
            p.clock = 0.0
            yield from glide([(b, p.cx + (35 if b.cx > p.cx else -35) * s, 140 * s) for b in live], max(0.2, top * 0.9))
            n = 0
            for b in live:
                if n < 2 and may_kill():
                    kill(b, sign(b.cx - p.cx))
                    n += 1
            for b in alive():
                b.anim = b.style
            yield from glide([pull_away(b, sign(b.cx - p.cx)) for b in alive()], 0.3)
            yield from settle(p)
            p.anim = "idle"

        def bat_hit():
            b = rng.choice(alive())
            side = sign(b.cx - p.cx)
            look(b)
            yield from glide([(b, inside(p.cx + side * 130 * s), 260 * s)], 0.25)
            yield from glide([(b, p.cx + side * 50 * s, 70 * s)], 0.22)
            burst(p.cx + side * 25 * s, area.bottom() - GROUND_OFFSET - 80 * s)
            knock_back(p, -side, 480, "shock")
            yield from glide([(b, inside(p.cx + side * 230 * s), 240 * s)], 0.35)
            yield from settle(p)
            p.anim = "fail"
            yield 0.45
            p.anim = "idle"
            look()

        def double_hit():
            live = alive()
            if len(live) < 2:
                yield from bat_hit()
                return
            a, c = live[0], live[1]
            yield from glide([(a, inside(p.cx - 230 * s), 200 * s), (c, inside(p.cx + 230 * s), 200 * s)], 0.3)
            yield from glide([(a, p.cx - 45 * s, 70 * s), (c, p.cx + 45 * s, 70 * s)], 0.22)
            burst(p.cx, area.bottom() - GROUND_OFFSET - 80 * s)
            p.launch(0, 600 * s, "shock", thrown=True)                      # squeezed, he is flung up
            yield from glide([(a, inside(p.cx - 260 * s), 260 * s), (c, inside(p.cx + 260 * s), 260 * s)], 0.35)
            yield from settle(p)
            p.anim = "fail"
            yield 0.6
            p.anim = "idle"

        def circle():
            """They circle above him; he turns on the spot, grimacing."""
            live = alive()
            for b in live:
                b.anim = b.style
            t0, a0 = 0.0, rng.uniform(0, 6.28)
            p.anim = "grimace"
            while t0 < 1.5:
                t0 += F["dt"]
                for i, b in enumerate(live):
                    ang = a0 + t0 * 5.5 + i * 6.283 / len(live)
                    b.cx = inside(p.cx + math.cos(ang) * 230 * s)
                    b.base_h = (200 + 60 * math.sin(ang)) * s
                    if abs(math.sin(ang)) > 0.2:
                        b.facing = -sign(math.sin(ang))
                p.facing = 1 if int(t0 * 5) % 2 == 0 else -1               # he follows them with his eyes
                yield 0
            p.anim = "idle"
            look()

        table = {"dive_dodge": dive_dodge, "dive_slash": dive_slash, "swarm_rush": swarm_rush,
                 "bat_hit": bat_hit, "double_hit": double_hit, "circle": circle}

        # ---- the opening: they swoop in
        yield from glide(hover_spots(), 0.9)
        look()
        p.anim = "grimace"
        self._show_bubble(t("fight_start_bat"), 3500)
        yield 0.9
        p.anim = "idle"
        yield 0.3

        # ---- the exchanges (the last bat is kept for the finale)
        last = None
        for _ in range(rng.randint(*BEATS)):
            if len(alive()) <= 1:
                break
            last = rng.choice([n for n in table if n != last])
            F["beat"] = last
            yield from table[last]()
            state["beats"] += 1
            if alive():
                yield from regroup(0.4)
            yield 0.1

        # ---- the finale
        look()
        if bats_win:
            live = alive()
            n = len(live)
            yield from glide([(b, inside(p.cx + (i - (n - 1) / 2) * 140 * s), 280 * s) for i, b in enumerate(live)], 0.4)
            for b in live:
                b.anim = b.style
            yield from glide([(b, p.cx + (i - (n - 1) / 2) * 50 * s, 70 * s) for i, b in enumerate(live)], 0.22)
            burst(p.cx, area.bottom() - GROUND_OFFSET - 80 * s)
            knock_back(p, rng.choice((-1, 1)), 1000, "shock")
            yield from glide([(b, inside(p.cx + (i - (n - 1) / 2) * 260 * s), 300 * s) for i, b in enumerate(live)], 0.4)
            yield from settle(p)
            p.anim = "cry"
            self._show_bubble(t("fight_lose_bat"), 4000)
            t0 = 0.0
            while t0 < 2.4:                                                # they circle, victorious
                t0 += F["dt"]
                for i, b in enumerate(live):
                    ang = t0 * 6 + i * 6.283 / n
                    b.cx = inside(p.cx + math.cos(ang) * 240 * s)
                    b.base_h = (210 + 55 * math.sin(ang)) * s
                    if abs(math.sin(ang)) > 0.2:
                        b.facing = -sign(math.sin(ang))
                yield 0
            yield from glide([(b, b.cx + (i - 1) * 300 * s, area.height() * 1.1) for i, b in enumerate(live)], 0.7)
            for b in live:
                b.widget.hide()
                b.alive = False
        else:
            live = alive()
            n = len(live)
            yield from glide([(b, inside(p.cx + (i - (n - 1) / 2) * 260 * s), 270 * s) for i, b in enumerate(live)], 0.35)
            top = hop(p, 0, 190, "attack")
            p.clock = 0.0
            yield from glide([(b, p.cx + (i - (n - 1) / 2) * 60 * s, 150 * s) for i, b in enumerate(live)], max(0.25, top * 0.9))
            for b in live:
                kill(b, sign(b.cx - p.cx))
            yield from settle(p)
            p.anim = "idle"
            yield 0.4
            p.facing = -p.facing
            p.anim = "hype"
            p.clock = 0.0
            self._show_bubble(t("fight_win"), 4000)
            yield 2.4
        p.anim = "idle"
        yield 0.2
