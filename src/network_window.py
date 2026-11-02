"""
network_window.py
-----------------
Compact network overlay for Prinaka: latency (ms) and live upload / download
speeds, without totals. Meant to stay on top of an online game or a call.

- never takes the keyboard focus, so opening it does not pull a game out of focus
- the lock button makes it click-through (mouse clicks reach the window below);
  close it from the Prinny menu or the tray icon to unlock it
- latency is probed every 2 seconds in a background thread
"""

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt5.QtCore import Qt, QTimer

from system_stats import NetworkMonitor, measure_latency
from floating import FloatingWindow
from poller import BackgroundPoller
from stat_widgets import BLUE, GREEN, MUTED, SpeedRow, latency_color, make_label
from utils import t


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_WIDTH       = 230
REFRESH_INTERVAL_MS = 1000
LATENCY_INTERVAL_S  = 2


class NetworkWindow(FloatingWindow):
    """
    Small always-on-top latency and bandwidth overlay.

    Args:
        config: Optional ConfigManager used to remember the position.
    """

    STYLE_CONTAINER = """
        QFrame#container {
            background: rgba(24, 24, 37, 205);
            border: 1px solid rgba(255, 255, 255, 30);
            border-radius: 8px;
        }
    """

    STYLE_BUTTON = (
        "QPushButton { color: #a6adc8; background: transparent; border: none; font-size: 13px; }"
        "QPushButton:hover { color: white; }"
    )

    def __init__(self, config=None):
        super().__init__(
            config, "net_window_pos",
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(WINDOW_WIDTH)

        self._network    = NetworkMonitor()
        self._locked     = False    # click-through
        self._reflagging = False    # True while changing window flags (hide/show is expected)

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)

        self._poller = BackgroundPoller(self._read_latency, LATENCY_INTERVAL_S, self)
        self._poller.updated.connect(self._on_latency)

        self._restore_position()

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
        body.setContentsMargins(10, 6, 6, 8)
        body.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(0)
        self._latency = make_label(f"color: {MUTED}; font-size: 15px; font-weight: bold;")
        self._latency.setText("📡 …")
        header.addWidget(self._latency)
        header.addStretch()

        self._lock_btn = QPushButton("🔓")
        self._lock_btn.setFixedSize(24, 24)
        self._lock_btn.setStyleSheet(self.STYLE_BUTTON)
        self._lock_btn.setToolTip(t("net_lock_tip"))
        self._lock_btn.clicked.connect(self._toggle_lock)
        header.addWidget(self._lock_btn)

        close_btn = QPushButton("✖")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(self.STYLE_BUTTON)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        body.addLayout(header)

        self._up   = SpeedRow("⬆️", BLUE)
        self._down = SpeedRow("⬇️", GREEN)
        body.addWidget(self._up)
        body.addWidget(self._down)

    # -----------------------------------------------------------------------
    # Click-through lock
    # -----------------------------------------------------------------------

    def _set_locked(self, locked: bool) -> None:
        """Switch click-through on or off without restarting the measurements."""
        self._locked = locked
        self._lock_btn.setText("🔒" if locked else "🔓")

        was_visible = self.isVisible()
        pos = self.pos()
        self._reflagging = True
        self.setWindowFlag(Qt.WindowTransparentForInput, locked)   # this hides the window
        if was_visible:
            self.show()
            self.move(pos)
        self._reflagging = False

    def _toggle_lock(self) -> None:
        self._set_locked(not self._locked)

    # -----------------------------------------------------------------------
    # Measurements
    # -----------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._reflagging:
            return
        self._network = NetworkMonitor()   # a long pause would skew the first speed
        self._up.clear_history()
        self._down.clear_history()
        self._refresh()
        self._timer.start(REFRESH_INTERVAL_MS)
        self._poller.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self._reflagging:
            return
        self._timer.stop()
        self._poller.stop()
        if self._locked:        # a closed overlay always comes back unlocked
            self._set_locked(False)

    def _refresh(self) -> None:
        speed = self._network.get_speeds()
        self._up.update_speed(speed["sent_speed"], speed["sent_bps"])
        self._down.update_speed(speed["recv_speed"], speed["recv_bps"])

    def _read_latency(self, cycle: int) -> dict:
        """Run in the background thread (see BackgroundPoller)."""
        return {"latency": measure_latency()}

    def _on_latency(self, data: dict) -> None:
        latency = data["latency"]
        text    = f"{latency} ms" if latency >= 0 else t("info_na")
        self._latency.setText(f"📡 {text}")
        self._latency.setStyleSheet(
            f"background: transparent; color: {latency_color(latency)};"
            " font-size: 15px; font-weight: bold;"
        )
