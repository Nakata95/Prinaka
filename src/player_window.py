"""
player_window.py
----------------
Mini media player for Prinaka: cover art, title, artist, progress bar and
previous / play-pause / next buttons for Spotify (or any media app, see the
"Spotify only" option).

- never takes the keyboard focus, so it can stay over a game or a document
- click or drag on the progress bar to seek
- the track is read once a second in a background thread
"""

import time

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget
from PyQt5.QtCore import Qt, QTimer, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QPainterPath, QPixmap, QColor, QFontMetrics

import media
from floating import FloatingWindow
from poller import BackgroundPoller
from stat_widgets import BLUE, GREEN, MUTED, make_label
from utils import t


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_WIDTH   = 390
COVER_SIZE     = 108
POLL_INTERVAL_S = 1
TICK_MS        = 250
# Next repeat mode when the button is clicked
REPEAT_CYCLE   = {media.REPEAT_NONE: media.REPEAT_LIST, media.REPEAT_LIST: media.REPEAT_TRACK,
                  media.REPEAT_TRACK: media.REPEAT_NONE}
SEEK_SETTLE_S  = 2.0   # keep the dragged position on screen until the player catches up


def format_time(seconds: float) -> str:
    """12.0 -> '0:12', 3725 -> '1:02:05'."""
    seconds = max(0, int(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class CoverArt(QWidget):
    """Rounded album cover; shows a note when there is no image."""

    def __init__(self, size: int = COVER_SIZE):
        super().__init__()
        self.setFixedSize(size, size)
        self._pixmap = None

    def set_image(self, data) -> None:
        pixmap = QPixmap()
        self._pixmap = pixmap if data and pixmap.loadFromData(data) else None
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect())

        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        painter.setClipPath(path)

        if self._pixmap:
            scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap(int((self.width() - scaled.width()) / 2),
                               int((self.height() - scaled.height()) / 2), scaled)
        else:
            painter.fillRect(rect, QColor(49, 50, 68))
            painter.setPen(QColor(MUTED))
            font = painter.font()
            font.setPixelSize(int(self.height() * 0.45))
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "♪")


class SeekBar(QWidget):
    """Thin progress bar: click or drag to pick a position (emits seeked(fraction))."""

    seeked = pyqtSignal(float)

    HEIGHT = 20

    def __init__(self):
        super().__init__()
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self._fraction = 0.0
        self._dragging = False
        self._enabled  = False

    def set_fraction(self, fraction: float) -> None:
        if not self._dragging:
            self._fraction = max(0.0, min(1.0, fraction))
            self.update()

    def set_seekable(self, seekable: bool) -> None:
        self._enabled = seekable
        self.update()

    def _fraction_at(self, x: float) -> float:
        return max(0.0, min(1.0, x / max(1, self.width())))

    def mousePressEvent(self, event) -> None:
        if self._enabled and event.button() == Qt.LeftButton:
            self._dragging = True
            self._fraction = self._fraction_at(event.x())
            self.update()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._fraction = self._fraction_at(event.x())
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self._dragging = False
            self.seeked.emit(self._fraction)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        h = 6
        y = (self.height() - h) / 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(69, 71, 90))
        painter.drawRoundedRect(QRectF(0, y, self.width(), h), 3, 3)
        painter.setBrush(QColor(GREEN))
        painter.drawRoundedRect(QRectF(0, y, self.width() * self._fraction, h), 3, 3)
        if self._enabled and (self._dragging or self.underMouse()):
            painter.setBrush(QColor("white"))
            painter.drawEllipse(QRectF(self.width() * self._fraction - 7, self.height() / 2 - 7, 14, 14))

    def enterEvent(self, event) -> None:
        self.update()

    def leaveEvent(self, event) -> None:
        self.update()


class ModeButton(QPushButton):
    """
    Round toggle button whose state is easy to read.

    Off: dimmed icon. On: icon on a colored disc with a dot underneath.
    An optional badge (like the "1" of a single-track loop) sits in the corner.
    """

    def __init__(self, icon: str, size: int):
        super().__init__(icon)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self._color = None
        self._badge = ""

    def set_mode(self, color=None, badge: str = "") -> None:
        """Show the button as on (with this color) or off (color None)."""
        self._color = color
        self._badge = badge
        self.update()

    def enterEvent(self, event) -> None:
        self.update()

    def leaveEvent(self, event) -> None:
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(Qt.NoPen)

        if self._color:
            disc = QColor(self._color)
            disc.setAlpha(80)
            painter.setBrush(disc)
            painter.drawEllipse(rect)
        elif self.underMouse() and self.isEnabled():
            painter.setBrush(QColor(255, 255, 255, 25))
            painter.drawEllipse(rect)

        painter.setOpacity(1.0 if self._color or self.underMouse() else 0.5)
        if not self.isEnabled():
            painter.setOpacity(0.25)
        font = self.font()
        font.setPixelSize(int(self.height() * 0.5))
        painter.setFont(font)
        painter.setPen(QColor("#cdd6f4"))
        painter.drawText(rect, Qt.AlignCenter, self.text())
        painter.setOpacity(1.0)

        if self._color:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(self._color))
            painter.drawEllipse(QRectF(self.width() / 2 - 2.5, self.height() - 7, 5, 5))

        if self._badge:
            d = self.height() * 0.42
            badge = QRectF(self.width() - d, 0, d, d)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(self._color or "#cdd6f4"))
            painter.drawEllipse(badge)
            font.setPixelSize(int(d * 0.75))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#1e1e2e"))
            painter.drawText(badge, Qt.AlignCenter, self._badge)


class ElidedLabel(QLabel):
    """Single-line label that ends with … instead of widening the window."""

    def __init__(self, style: str = ""):
        super().__init__()
        self.setStyleSheet(f"background: transparent; {style}")
        self.setMinimumWidth(10)
        self._full = ""

    def setText(self, text: str) -> None:
        self._full = text
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        shown = QFontMetrics(self.font()).elidedText(self._full, Qt.ElideRight, max(10, self.width()))
        super().setText(shown)
        self.setToolTip(self._full if shown != self._full else "")


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

class PlayerWindow(FloatingWindow):
    """
    Always-on-top mini player.

    Args:
        config: ConfigManager (position and the 'media_spotify_only' option).
    """

    STYLE_CONTAINER = """
        QFrame#container {
            background: rgba(24, 24, 37, 235);
            border: 1px solid rgba(255, 255, 255, 30);
            border-radius: 12px;
        }
    """

    STYLE_BUTTON = (
        "QPushButton { color: #a6adc8; background: transparent; border: none; font-size: 16px; }"
        "QPushButton:hover { color: white; }"
    )
    STYLE_CONTROL = (
        "QPushButton { color: #cdd6f4; background: transparent; border: none; font-size: 26px; }"
        "QPushButton:hover { color: white; background: rgba(255, 255, 255, 25); border-radius: 22px; }"
        "QPushButton:disabled { color: #585b70; }"
    )
    STYLE_PLAY = (
        "QPushButton { color: #1e1e2e; background: #cdd6f4; border: none; border-radius: 28px; font-size: 26px; }"
        "QPushButton:disabled { background: #45475a; color: #6c7086; }"
        "QPushButton:hover { background: white; }"
    )

    def __init__(self, config=None):
        super().__init__(
            config, "player_window_pos",
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(WINDOW_WIDTH)

        self._config   = config
        self._source   = media.SOURCE_SPOTIFY
        self._state    = None     # last snapshot from the background reading
        self._state_at = 0.0      # monotonic time of that snapshot
        self._key      = None
        self._app_running = False
        self._seek_hold = (0.0, 0.0)   # (until, position) after a user seek

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._poller = BackgroundPoller(self._read, POLL_INTERVAL_S, self, com=False)
        self._poller.updated.connect(self._on_state)

        self._restore_position()
        self._show_state(None)

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        container = QFrame(self)
        container.setObjectName("container")
        container.setStyleSheet(self.STYLE_CONTAINER)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        body = QVBoxLayout(container)
        body.setContentsMargins(16, 14, 10, 14)
        body.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(16)
        self._cover = CoverArt()
        top.addWidget(self._cover, 0, Qt.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(4)
        self._title  = ElidedLabel("color: #cdd6f4; font-size: 19px; font-weight: bold;")
        self._artist = ElidedLabel(f"color: {MUTED}; font-size: 15px;")
        texts.addWidget(self._title)
        texts.addWidget(self._artist)
        texts.addStretch()
        top.addLayout(texts, 1)

        close_btn = QPushButton("✖")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(self.STYLE_BUTTON)
        close_btn.clicked.connect(self.hide)
        top.addWidget(close_btn, 0, Qt.AlignTop)
        body.addLayout(top)

        progress = QHBoxLayout()
        progress.setSpacing(10)
        progress.setContentsMargins(0, 0, 4, 0)
        self._elapsed = make_label(f"color: {MUTED}; font-size: 13px;")
        self._total   = make_label(f"color: {MUTED}; font-size: 13px;")
        self._elapsed.setFixedWidth(48)
        self._total.setFixedWidth(48)
        self._elapsed.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._seek = SeekBar()
        self._seek.seeked.connect(self._on_seek)
        progress.addWidget(self._elapsed)
        progress.addWidget(self._seek, 1)
        progress.addWidget(self._total)
        body.addLayout(progress)

        controls = QHBoxLayout()
        controls.setSpacing(14)
        controls.addStretch()
        self._shuffle_btn = ModeButton("🔀", 40)
        self._shuffle_btn.setToolTip(t("player_shuffle"))
        self._repeat_btn = ModeButton("🔁", 40)
        self._repeat_btn.setToolTip(t("player_repeat"))
        self._prev_btn = self._control_button("⏮", self.STYLE_CONTROL, 44, t("player_prev"))
        self._play_btn = self._control_button("▶", self.STYLE_PLAY, 56, t("player_play"))
        self._next_btn = self._control_button("⏭", self.STYLE_CONTROL, 44, t("player_next"))
        self._prev_btn.clicked.connect(lambda: self._command("previous"))
        self._play_btn.clicked.connect(self._on_play_pause)
        self._next_btn.clicked.connect(lambda: self._command("next"))
        self._shuffle_btn.clicked.connect(self._on_shuffle)
        self._repeat_btn.clicked.connect(self._on_repeat)
        for button in (self._shuffle_btn, self._prev_btn, self._play_btn, self._next_btn, self._repeat_btn):
            controls.addWidget(button)
        controls.addStretch()
        controls.setContentsMargins(0, 0, 4, 0)
        body.addLayout(controls)

    def _control_button(self, text: str, style: str, size: int, tip: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedSize(size, size)
        button.setStyleSheet(style)
        button.setToolTip(tip)
        button.setCursor(Qt.PointingHandCursor)
        return button

    # -----------------------------------------------------------------------
    # Reading
    # -----------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        spotify_only = self._config.get("media_spotify_only") if self._config else True
        self._source = media.SOURCE_SPOTIFY if spotify_only else media.SOURCE_ANY
        self._show_state(None)
        self._timer.start(TICK_MS)
        self._poller.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()
        self._poller.stop()

    def _read(self, cycle: int) -> dict:
        """Run in the background thread (see BackgroundPoller)."""
        state = media.get_media_state(self._source, with_thumbnail=True)
        running = state is not None or (self._source == media.SOURCE_SPOTIFY and media.is_spotify_running())
        return {"state": state, "app_running": running}

    def _on_state(self, data: dict) -> None:
        state = data["state"]
        self._state    = state
        self._state_at = time.monotonic()
        self._app_running = data["app_running"]
        self._show_state(state)

    # -----------------------------------------------------------------------
    # Display
    # -----------------------------------------------------------------------

    def _show_state(self, state) -> None:
        """Fill the labels and buttons from a snapshot (None = nothing to play)."""
        has_track = state is not None
        for widget in (self._shuffle_btn, self._prev_btn, self._play_btn, self._next_btn, self._repeat_btn):
            widget.setEnabled(has_track)
        self._seek.set_seekable(has_track and state["duration"] > 0)

        if not has_track:
            self._key = None
            if self._source != media.SOURCE_SPOTIFY:
                self._title.setText(t("player_none_any"))
            else:
                self._title.setText(t("player_idle_spotify") if self._app_running else t("player_none_spotify"))
            self._artist.setText("")
            self._cover.set_image(None)
            self._play_btn.setText("▶")
            self._shuffle_btn.set_mode(None)
            self._repeat_btn.set_mode(None)
            self._seek.set_fraction(0)
            self._elapsed.setText("0:00")
            self._total.setText("0:00")
            return

        if state["key"] != self._key:   # new track
            self._key = state["key"]
            self._title.setText(state["title"])
            self._artist.setText(state["artist"] or t("player_unknown_artist"))
            self._cover.set_image(state["thumbnail"])
        elif state["thumbnail"] and self._cover._pixmap is None:
            self._cover.set_image(state["thumbnail"])   # cover that arrived late

        self._play_btn.setText("⏸" if state["playing"] else "▶")
        self._play_btn.setToolTip(t("player_pause") if state["playing"] else t("player_play"))
        self._total.setText(format_time(state["duration"]))
        self._shuffle_btn.set_mode(GREEN if state["shuffle"] else None)
        self._shuffle_btn.setToolTip(t("player_shuffle_on") if state["shuffle"] else t("player_shuffle"))
        if state["repeat"] == media.REPEAT_TRACK:
            self._repeat_btn.set_mode(BLUE, "1")
            self._repeat_btn.setToolTip(t("player_repeat_track"))
        elif state["repeat"] == media.REPEAT_LIST:
            self._repeat_btn.set_mode(GREEN)
            self._repeat_btn.setToolTip(t("player_repeat_all"))
        else:
            self._repeat_btn.set_mode(None)
            self._repeat_btn.setToolTip(t("player_repeat"))
        self._tick()

    def _position(self) -> float:
        """Position now: the last snapshot plus the time elapsed since, while playing."""
        state = self._state
        if not state:
            return 0.0
        until, held = self._seek_hold
        if time.monotonic() < until:
            return held
        position = state["position"]
        if state["playing"]:
            position += time.monotonic() - self._state_at
        return min(position, state["duration"]) if state["duration"] > 0 else position

    def _tick(self) -> None:
        state = self._state
        if not state:
            return
        position = self._position()
        self._elapsed.setText(format_time(position))
        if state["duration"] > 0:
            self._seek.set_fraction(position / state["duration"])

    # -----------------------------------------------------------------------
    # Commands
    # -----------------------------------------------------------------------

    def _command(self, command: str, value: float = 0.0) -> None:
        media.send_command(self._source, command, value)

    def _on_play_pause(self) -> None:
        self._command("toggle")
        if self._state:
            self._update_state(playing=not self._state["playing"])

    def _update_state(self, **changes) -> None:
        """Show a change right away; the next reading confirms it."""
        self._state = dict(self._state, position=self._position(), **changes)
        self._state_at = time.monotonic()
        self._show_state(self._state)

    def _on_shuffle(self) -> None:
        if not self._state:
            return
        on = not self._state["shuffle"]
        self._command("shuffle", on)
        self._update_state(shuffle=on)

    def _on_repeat(self) -> None:
        """Cycle off -> loop everything -> loop this track -> off."""
        if not self._state:
            return
        mode = REPEAT_CYCLE[self._state["repeat"]]
        self._command("repeat", mode)
        self._update_state(repeat=mode)

    def _on_seek(self, fraction: float) -> None:
        if not self._state or self._state["duration"] <= 0:
            return
        target = fraction * self._state["duration"]
        self._seek_hold = (time.monotonic() + SEEK_SETTLE_S, target)
        self._command("seek", target)
        self._tick()
