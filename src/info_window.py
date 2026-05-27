"""
info_window.py
--------------
System information overlay window for Prinaka.

Displays real-time system stats in a draggable, frameless window:
- CPU usage and temperature
- RAM usage
- Disk usage
- Network speed and latency
- Recycle bin size
- Mouse click and keystroke counters

Refreshes every second via a QTimer.
"""

from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
)
from PyQt5.QtCore import Qt, QTimer, QPoint

from system_stats import (
    get_cpu_usage,
    get_cpu_temperature,
    get_ram_usage,
    get_disk_usage,
    get_recycle_bin_stats,
    NetworkMonitor,
)
from listeners import get_click_count, get_key_count
from utils import t


# ---------------------------------------------------------------------------
# Info Window
# ---------------------------------------------------------------------------

class InfoWindow(QWidget):
    """
    Frameless, translucent system stats window.

    Stays always on top and can be dragged anywhere on screen.
    Refreshes all stats every second.
    """

    STYLE_CONTAINER = (
        "background: rgba(0, 0, 0, 180);"
        "border-radius: 6px;"
    )

    STYLE_LABEL = (
        "color: white;"
        "font-size: 13px;"
        "padding: 4px 8px 8px 8px;"
        "background: transparent;"
    )

    STYLE_CLOSE = (
        "QPushButton { color: white; background: transparent; border: none; font-size: 14px; }"
        "QPushButton:hover { color: red; }"
    )

    REFRESH_INTERVAL_MS = 1000

    def __init__(self):
        super().__init__(None)

        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        # --- Network monitor ---
        self._network = NetworkMonitor()

        # --- Container widget avec fond arrondi ---
        self._container = QWidget(self)
        self._container.setStyleSheet(self.STYLE_CONTAINER)

        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Barre du haut : titre vide + croix
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(8, 4, 4, 0)
        top_bar.addStretch()

        self._close_btn = QPushButton("✖")
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setStyleSheet(self.STYLE_CLOSE)
        self._close_btn.clicked.connect(self.hide)
        top_bar.addWidget(self._close_btn)

        container_layout.addLayout(top_bar)

        # Label des stats
        self._label = QLabel(t("info_loading"))
        self._label.setStyleSheet(self.STYLE_LABEL)
        self._label.setWordWrap(True)
        container_layout.addWidget(self._label)

        # Layout principal de la fenêtre
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._container)

        # --- Timer de refresh ---
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(self.REFRESH_INTERVAL_MS)
        self._refresh()

        # --- Drag ---
        self._dragging       = False
        self._drag_start_pos = QPoint()

    # --- Stats ---

    def _refresh(self) -> None:
        """Fetch all system stats and update the display label."""
        cpu     = get_cpu_usage()
        temp    = get_cpu_temperature()
        ram     = get_ram_usage()
        disk    = get_disk_usage("/")
        recycle = get_recycle_bin_stats()
        net     = self._network.get_stats()
        clicks  = get_click_count()
        keys    = get_key_count()

        latency = f"{net['latency_ms']} ms" if net["latency_ms"] >= 0 else t("info_na")

        text = (
            f"{t('info_cpu')}  : {cpu}%\n"
            f"{t('info_ram')}  : {ram['percent']}%"
            f" ({ram['used_gb']} GB / {ram['total_gb']} GB)\n"
            f"{t('info_disk')} : {disk['used_gb']} GB / {disk['total_gb']} GB"
            f" ({t('info_disk_free')}: {disk['free_gb']} GB,"
            f" {disk['free_percent']:.1f}%)\n"
            f"{t('info_temp')} : {temp}\n"
            f"{t('info_recycle')} : {recycle}\n"
            f"{t('info_clicks')} : {clicks} | "
            f"{t('info_keys')} : {keys}\n"
            f"{t('info_latency')} : {latency}\n"
            f"{t('info_upload')} : {net['sent_total']} ({net['sent_speed']})\n"
            f"{t('info_download')} : {net['recv_total']} ({net['recv_speed']})"
        )

        self._label.setText(text)
        self._label.adjustSize()
        self._container.adjustSize()
        self.adjustSize()

    # --- Drag ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging       = True
            self._drag_start_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.move(event.globalPos() - self._drag_start_pos)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False