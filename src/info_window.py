"""
info_window.py
--------------
System information overlay window for Prinaka.

A draggable, frameless, always-on-top dashboard showing:
- CPU and RAM usage (gauge + history graph)
- CPU temperature
- Every local drive
- Network speeds (with history), latency and totals
- Recycle bin size, uptime, battery, click and keystroke counters

Fast values refresh every second in the GUI thread. Slow ones (latency,
temperature, drives, recycle bin) are read in a background thread so the
window never freezes, and nothing runs while the window is hidden.
"""

import psutil
from PyQt5.QtWidgets import (
    QApplication, QFrame, QVBoxLayout, QHBoxLayout, QPushButton
)
from PyQt5.QtCore import Qt, QTimer

from system_stats import (
    get_cpu_usage,
    get_cpu_temperature_c,
    get_ram_usage,
    get_fixed_drives,
    get_recycle_bin_stats,
    get_uptime_seconds,
    get_battery,
    measure_latency,
    NetworkMonitor,
)
from listeners import get_click_count, get_key_count
from quotes import format_number
from utils import t
from floating import FloatingWindow, GRAB_WIDTH, GRAB_HEIGHT   # noqa: F401 (re-exported)
from poller import BackgroundPoller
from stat_widgets import (
    GREEN, YELLOW, RED, BLUE, TEAL, MUTED,
    level_color, latency_color, format_bytes, make_label,
    MetricCard, SpeedRow,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_WIDTH       = 340
SLOW_INTERVAL_S    = 5       # latency / temperature / drives
RECYCLE_EVERY      = 6       # slow cycles between two recycle bin scans (30 s)

# temperature gauge range and colour thresholds, in °C
TEMP_MIN, TEMP_MAX = 30.0, 100.0
TEMP_WARN, TEMP_CRIT = 70.0, 85.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_uptime(seconds: int) -> str:
    """Format a duration as '3 d 4 h' or '12 min' using the active language."""
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} {t('info_unit_d')} {hours} {t('info_unit_h')}"
    if hours:
        return f"{hours} {t('info_unit_h')} {minutes} {t('info_unit_min')}"
    return f"{minutes} {t('info_unit_min')}"


# ---------------------------------------------------------------------------
# Info Window
# ---------------------------------------------------------------------------

class InfoWindow(FloatingWindow):
    """
    Frameless, translucent system dashboard.

    Stays always on top and can be dragged anywhere on screen; its position
    is remembered between sessions.

    Args:
        config: Optional ConfigManager used to remember the window position.
    """

    STYLE_CONTAINER = """
        QFrame#container {
            background: rgba(24, 24, 37, 235);
            border: 1px solid rgba(255, 255, 255, 30);
            border-radius: 10px;
        }
    """

    STYLE_BUTTON = (
        "QPushButton { color: #a6adc8; background: transparent; border: none; font-size: 14px; }"
        "QPushButton:hover { color: white; }"
    )

    REFRESH_INTERVAL_MS = 1000

    def __init__(self, config=None):
        super().__init__(
            config, "info_window_pos",
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setFixedWidth(WINDOW_WIDTH)

        self._network     = NetworkMonitor()
        self._slow        = {}        # last data from the background worker
        self._drive_cards = {}        # mount -> MetricCard
        self._report      = ""        # text copied by the clipboard button
        self._fast        = None      # (cpu, ram, speed) of the last refresh

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)

        self._worker = BackgroundPoller(self._read_slow, SLOW_INTERVAL_S, self)
        self._worker.updated.connect(self._on_slow_stats)

        self._restore_position()

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._container = QFrame(self)
        self._container.setObjectName("container")
        self._container.setStyleSheet(self.STYLE_CONTAINER)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._container)

        body = QVBoxLayout(self._container)
        body.setContentsMargins(14, 8, 14, 12)
        body.setSpacing(10)

        # Header: title, copy, close
        header = QHBoxLayout()
        self._title = make_label("color: white; font-size: 13px; font-weight: bold;")
        header.addWidget(self._title)
        header.addStretch()

        self._copy_btn = QPushButton("📋")
        self._copy_btn.setFixedSize(24, 24)
        self._copy_btn.setStyleSheet(self.STYLE_BUTTON)
        self._copy_btn.clicked.connect(self._copy_report)
        header.addWidget(self._copy_btn)

        close_btn = QPushButton("✖")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(self.STYLE_BUTTON)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        body.addLayout(header)

        # CPU / RAM / temperature
        self._cpu  = MetricCard(spark_color=BLUE, spark_max=100)
        self._ram  = MetricCard(spark_color=TEAL, spark_max=100)
        self._temp = MetricCard()
        for card in (self._cpu, self._ram, self._temp):
            body.addWidget(card)

        # Drives (filled when the first slow stats arrive)
        self._drives_box = QVBoxLayout()
        self._drives_box.setSpacing(8)
        body.addLayout(self._drives_box)

        # Network
        net_head = QHBoxLayout()
        self._net_title   = make_label("color: #cdd6f4; font-size: 12px;")
        self._net_latency = make_label(f"color: {MUTED}; font-size: 12px; font-weight: bold;")
        net_head.addWidget(self._net_title)
        net_head.addStretch()
        net_head.addWidget(self._net_latency)
        body.addLayout(net_head)

        self._up   = SpeedRow("⬆️", BLUE)
        self._down = SpeedRow("⬇️", GREEN)
        body.addWidget(self._up)
        body.addWidget(self._down)

        self._net_totals = make_label(f"color: {MUTED}; font-size: 11px;")
        body.addWidget(self._net_totals)

        # Footer
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255, 255, 255, 25);")
        body.addWidget(sep)

        self._footer_a = make_label("color: #cdd6f4; font-size: 12px;")
        self._footer_b = make_label("color: #cdd6f4; font-size: 12px;")
        body.addWidget(self._footer_a)
        body.addWidget(self._footer_b)

        self._retranslate()

    def _retranslate(self) -> None:
        """Apply the active language to the static titles."""
        self._title.setText(t("info_title"))
        self._copy_btn.setToolTip(t("info_copy"))
        self._cpu.set_title(t("info_cpu"))
        self._ram.set_title(t("info_ram"))
        self._temp.set_title(t("info_temp"))
        self._net_title.setText(t("info_network"))
        for mount, card in self._drive_cards.items():
            card.set_title(t("info_drive").format(mount=mount))

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._network = NetworkMonitor()   # a long pause would skew the first speed
        for graph in (self._cpu, self._ram, self._up, self._down):
            graph.clear_history()
        self._retranslate()
        self._refresh()
        self._timer.start(self.REFRESH_INTERVAL_MS)
        self._worker.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()
        self._worker.stop()

    def _refresh(self) -> None:
        """Update the fast stats (cheap enough for the GUI thread)."""
        cpu   = get_cpu_usage()
        ram   = get_ram_usage()
        speed = self._network.get_speeds()

        self._cpu.update_metric(
            cpu / 100, f"{cpu:.0f}%",
            t("info_threads").format(n=psutil.cpu_count()),
            spark_value=cpu,
        )
        self._ram.update_metric(
            ram["percent"] / 100, f"{ram['percent']:.0f}%",
            f"{ram['used'] / 1024 ** 3:.1f} / {ram['total'] / 1024 ** 3:.1f} GB",
            spark_value=ram["percent"],
        )

        self._up.update_speed(speed["sent_speed"], speed["sent_bps"])
        self._down.update_speed(speed["recv_speed"], speed["recv_bps"])
        self._net_totals.setText(
            f"{t('info_total')} : ⬆️ {speed['sent_total']}   ⬇️ {speed['recv_total']}"
        )

        self._fast = (cpu, ram, speed)
        self._update_footer()

    def _update_footer(self) -> None:
        """Rebuild the footer lines and the clipboard report from the latest values."""
        cpu, ram, speed = self._fast
        clicks  = format_number(get_click_count())
        keys    = format_number(get_key_count())
        recycle = self._slow.get("recycle", t("info_loading"))
        uptime  = format_uptime(get_uptime_seconds())

        self._footer_a.setText(f"{t('info_recycle')} : {recycle}    ⏱ {uptime}")
        battery = self._slow.get("battery")
        battery_text = ""
        if battery:
            battery_text = f"    🔋 {battery['percent']:.0f}%" + (" ⚡" if battery["plugged"] else "")
        self._footer_b.setText(f"{t('info_clicks')} : {clicks}    {t('info_keys')} : {keys}{battery_text}")

        self._report = self._build_report(cpu, ram, speed, clicks, keys, recycle, uptime)

    def _read_slow(self, cycle: int) -> dict:
        """Slow readings, run in the background thread (see BackgroundPoller)."""
        data = {
            "latency": measure_latency(),
            "temp":    get_cpu_temperature_c(),
            "drives":  get_fixed_drives(),
            "battery": get_battery(),
        }
        if cycle % RECYCLE_EVERY == 0:
            data["recycle"] = get_recycle_bin_stats()
        return data

    def _on_slow_stats(self, data: dict) -> None:
        """Slot for BackgroundPoller.updated (runs on the GUI thread)."""
        self._slow.update(data)

        # Temperature
        temp = data.get("temp")
        if temp is None:
            self._temp.update_metric(None, t("info_na"))
        else:
            fraction = (temp - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)
            self._temp.update_metric(
                fraction, f"{temp:.0f}°C",
                warn=(TEMP_WARN - TEMP_MIN) / (TEMP_MAX - TEMP_MIN),
                crit=(TEMP_CRIT - TEMP_MIN) / (TEMP_MAX - TEMP_MIN),
            )

        # Latency
        latency = data.get("latency", -1)
        if latency < 0:
            self._net_latency.setText(f"📡 {t('info_na')}")
            color = MUTED
        else:
            self._net_latency.setText(f"📡 {latency} ms")
            color = latency_color(latency)
        self._net_latency.setStyleSheet(
            f"background: transparent; color: {color}; font-size: 12px; font-weight: bold;"
        )

        self._update_drives(data.get("drives", []))
        if self._fast:
            self._update_footer()   # shows recycle bin / battery

    def _update_drives(self, drives: list) -> None:
        mounts = [d["mount"] for d in drives]
        if mounts != list(self._drive_cards):
            for card in self._drive_cards.values():
                self._drives_box.removeWidget(card)
                card.deleteLater()
            self._drive_cards = {}
            for mount in mounts:
                card = MetricCard()
                card.set_title(t("info_drive").format(mount=mount))
                self._drives_box.addWidget(card)
                self._drive_cards[mount] = card
            QTimer.singleShot(0, self._resize_and_recenter)

        for drive in drives:
            self._drive_cards[drive["mount"]].update_metric(
                drive["percent"] / 100, f"{drive['percent']:.0f}%",
                t("info_free_of").format(free=format_bytes(drive["free"]),
                                         total=format_bytes(drive["total"])),
                warn=0.8, crit=0.9,
            )

    def _resize_and_recenter(self) -> None:
        """Fit the new content; keep the window centered if it was placed by center_on."""
        self.adjustSize()
        if self._center_rect is not None:
            self._center()

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------

    def _build_report(self, cpu, ram, speed, clicks, keys, recycle, uptime) -> str:
        lines = [
            f"{t('info_cpu')} : {cpu:.0f}%",
            f"{t('info_ram')} : {ram['percent']:.0f}% "
            f"({ram['used'] / 1024 ** 3:.1f} / {ram['total'] / 1024 ** 3:.1f} GB)",
        ]
        temp = self._slow.get("temp")
        lines.append(f"{t('info_temp')} : {f'{temp:.0f}°C' if temp is not None else t('info_na')}")
        for drive in self._slow.get("drives", []):
            lines.append(
                f"{t('info_drive').format(mount=drive['mount'])} : {drive['percent']:.0f}% "
                f"({t('info_free_of').format(free=format_bytes(drive['free']), total=format_bytes(drive['total']))})"
            )
        latency = self._slow.get("latency", -1)
        lines += [
            f"{t('info_latency')} : {f'{latency} ms' if latency >= 0 else t('info_na')}",
            f"{t('info_upload')} : {speed['sent_speed']} ({speed['sent_total']})",
            f"{t('info_download')} : {speed['recv_speed']} ({speed['recv_total']})",
            f"{t('info_recycle')} : {recycle}",
            f"⏱ {uptime}",
            f"{t('info_clicks')} : {clicks} | {t('info_keys')} : {keys}",
        ]
        return "\n".join(lines)

    def _copy_report(self) -> None:
        """Copy the current stats as plain text to the clipboard."""
        QApplication.clipboard().setText(self._report)
        self._copy_btn.setText("✔")
        QTimer.singleShot(1200, lambda: self._copy_btn.setText("📋"))
