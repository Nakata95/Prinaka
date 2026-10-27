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

import time
import threading
from collections import deque

import psutil
from PyQt5.QtWidgets import (
    QApplication, QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
)
from PyQt5.QtCore import Qt, QTimer, QPoint, QPointF, QRectF, QObject, pyqtSignal
from PyQt5.QtGui import QPainter, QPainterPath, QColor, QPen

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
from utils import t, get_total_screen_rect


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GREEN  = "#a6e3a1"
YELLOW = "#f9e2af"
RED    = "#f38ba8"
BLUE   = "#89b4fa"
TEAL   = "#94e2d5"
MUTED  = "#6c7086"

WINDOW_WIDTH       = 340
HISTORY_LENGTH     = 60      # seconds of graph history
SLOW_INTERVAL_S    = 5       # latency / temperature / drives
RECYCLE_EVERY      = 6       # slow cycles between two recycle bin scans (30 s)

# temperature gauge range and colour thresholds, in °C
TEMP_MIN, TEMP_MAX = 30.0, 100.0
TEMP_WARN, TEMP_CRIT = 70.0, 85.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def level_color(fraction: float, warn: float = 0.6, crit: float = 0.85) -> str:
    """Return green / yellow / red depending on how full a gauge is."""
    if fraction >= crit:
        return RED
    if fraction >= warn:
        return YELLOW
    return GREEN


def format_bytes(n: float) -> str:
    """Format a byte count (e.g. '64 GB', '1.8 TB')."""
    gb = n / (1024 ** 3)
    if gb >= 1000:
        return f"{gb / 1024:.1f} TB"
    return f"{gb:.0f} GB" if gb >= 10 else f"{gb:.1f} GB"


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


def _label(style: str = "") -> QLabel:
    lbl = QLabel()
    lbl.setStyleSheet(f"background: transparent; {style}")
    return lbl


# ---------------------------------------------------------------------------
# Drawing widgets
# ---------------------------------------------------------------------------

class UsageBar(QWidget):
    """Thin rounded gauge."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(6)
        self._fraction = 0.0
        self._color    = QColor(MUTED)

    def set_value(self, fraction: float | None, color: str) -> None:
        self._fraction = 0.0 if fraction is None else max(0.0, min(1.0, fraction))
        self._color    = QColor(color if fraction is not None else MUTED)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect   = QRectF(self.rect())
        radius = rect.height() / 2

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 28))
        painter.drawRoundedRect(rect, radius, radius)

        if self._fraction > 0:
            fill = QRectF(rect)
            fill.setWidth(max(rect.height(), rect.width() * self._fraction))
            painter.setBrush(self._color)
            painter.drawRoundedRect(fill, radius, radius)


class Sparkline(QWidget):
    """Small history graph, newest value on the right."""

    def __init__(self, color: str, height: int = 28, fixed_max: float | None = None):
        super().__init__()
        self.setFixedHeight(height)
        self._values    = deque(maxlen=HISTORY_LENGTH)
        self._color     = QColor(color)
        self._fixed_max = fixed_max

    def push(self, value: float) -> None:
        self._values.append(float(value))
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self.update()

    def paintEvent(self, event) -> None:
        count = len(self._values)
        if count < 2:
            return

        width, height = self.width(), self.height()
        top  = self._fixed_max or max(max(self._values), 1.0)
        step = width / (HISTORY_LENGTH - 1)
        points = [
            QPointF(width - (count - 1 - i) * step, height - 1 - (v / top) * (height - 2))
            for i, v in enumerate(self._values)
        ]

        line = QPainterPath(points[0])
        for point in points[1:]:
            line.lineTo(point)

        area = QPainterPath(line)
        area.lineTo(points[-1].x(), height)
        area.lineTo(points[0].x(), height)
        area.closeSubpath()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        fill = QColor(self._color)
        fill.setAlpha(55)
        painter.fillPath(area, fill)
        painter.setPen(QPen(self._color, 1.5))
        painter.drawPath(line)


class MetricCard(QWidget):
    """Title + value, gauge, optional detail line and optional history graph."""

    def __init__(self, spark_color: str | None = None, spark_max: float | None = None):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self._title = _label("color: #cdd6f4; font-size: 12px;")
        self._value = _label("color: white; font-size: 13px; font-weight: bold;")
        head.addWidget(self._title)
        head.addStretch()
        head.addWidget(self._value)
        layout.addLayout(head)

        self._bar = UsageBar()
        layout.addWidget(self._bar)

        self._detail = _label(f"color: {MUTED}; font-size: 11px;")
        layout.addWidget(self._detail)

        self._spark = Sparkline(spark_color, fixed_max=spark_max) if spark_color else None
        if self._spark:
            layout.addWidget(self._spark)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def update_metric(self, fraction: float | None, value: str, detail: str = "",
                      warn: float = 0.6, crit: float = 0.85,
                      spark_value: float | None = None) -> None:
        self._value.setText(value)
        self._bar.set_value(fraction, level_color(fraction or 0, warn, crit))
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        if self._spark is not None and spark_value is not None:
            self._spark.push(spark_value)

    def clear_history(self) -> None:
        if self._spark is not None:
            self._spark.clear()


class SpeedRow(QWidget):
    """Arrow + current speed + history graph (upload or download)."""

    def __init__(self, arrow: str, color: str):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        icon = _label("font-size: 12px;")
        icon.setText(arrow)
        icon.setFixedWidth(18)
        layout.addWidget(icon)

        self._speed = _label("color: white; font-size: 12px;")
        self._speed.setFixedWidth(88)
        layout.addWidget(self._speed)

        self._spark = Sparkline(color, height=22)
        layout.addWidget(self._spark, 1)

    def update_speed(self, text: str, bps: float) -> None:
        self._speed.setText(text)
        self._spark.push(bps)

    def clear_history(self) -> None:
        self._spark.clear()


# ---------------------------------------------------------------------------
# Background reader
# ---------------------------------------------------------------------------

class SlowStatsWorker(QObject):
    """
    Reads the slow stats in a background thread.

    Emits `updated(dict)` every few seconds with the keys latency (int ms,
    -1 if offline), temp (float °C or None), drives (list), battery
    (dict or None) and, every 30 seconds, recycle (str).
    """

    updated = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._generation = 0

    def start(self) -> None:
        self._generation += 1
        threading.Thread(target=self._run, args=(self._generation,), daemon=True).start()

    def stop(self) -> None:
        self._generation += 1   # makes the running thread exit

    def _run(self, generation: int) -> None:
        try:
            import pythoncom   # WMI (temperature) needs COM initialised in every thread
            pythoncom.CoInitialize()
        except ImportError:
            pythoncom = None

        try:
            self._loop(generation)
        finally:
            if pythoncom:
                pythoncom.CoUninitialize()

    def _loop(self, generation: int) -> None:
        cycle = 0
        while generation == self._generation:
            data = {
                "latency": measure_latency(),
                "temp":    get_cpu_temperature_c(),
                "drives":  get_fixed_drives(),
                "battery": get_battery(),
            }
            if cycle % RECYCLE_EVERY == 0:
                data["recycle"] = get_recycle_bin_stats()
            if generation != self._generation:
                return
            self.updated.emit(data)
            cycle += 1

            for _ in range(SLOW_INTERVAL_S * 10):   # interruptible sleep
                if generation != self._generation:
                    return
                time.sleep(0.1)


# ---------------------------------------------------------------------------
# Info Window
# ---------------------------------------------------------------------------

class InfoWindow(QWidget):
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
        super().__init__(None)
        self._config = config

        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setFixedWidth(WINDOW_WIDTH)

        self._network     = NetworkMonitor()
        self._slow        = {}        # last data from the background worker
        self._drive_cards = {}        # mount -> MetricCard
        self._report      = ""        # text copied by the clipboard button
        self._fast        = None      # (cpu, ram, speed) of the last refresh

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)

        self._worker = SlowStatsWorker(self)
        self._worker.updated.connect(self._on_slow_stats)

        self._dragging       = False
        self._drag_start_pos = QPoint()
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
        self._title = _label("color: white; font-size: 13px; font-weight: bold;")
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
        self._net_title   = _label("color: #cdd6f4; font-size: 12px;")
        self._net_latency = _label(f"color: {MUTED}; font-size: 12px; font-weight: bold;")
        net_head.addWidget(self._net_title)
        net_head.addStretch()
        net_head.addWidget(self._net_latency)
        body.addLayout(net_head)

        self._up   = SpeedRow("⬆️", BLUE)
        self._down = SpeedRow("⬇️", GREEN)
        body.addWidget(self._up)
        body.addWidget(self._down)

        self._net_totals = _label(f"color: {MUTED}; font-size: 11px;")
        body.addWidget(self._net_totals)

        # Footer
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255, 255, 255, 25);")
        body.addWidget(sep)

        self._footer_a = _label("color: #cdd6f4; font-size: 12px;")
        self._footer_b = _label("color: #cdd6f4; font-size: 12px;")
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

    def _on_slow_stats(self, data: dict) -> None:
        """Slot for SlowStatsWorker.updated (runs on the GUI thread)."""
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
            color = GREEN if latency < 60 else YELLOW if latency < 150 else RED
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
            QTimer.singleShot(0, self.adjustSize)

        for drive in drives:
            self._drive_cards[drive["mount"]].update_metric(
                drive["percent"] / 100, f"{drive['percent']:.0f}%",
                t("info_free_of").format(free=format_bytes(drive["free"]),
                                         total=format_bytes(drive["total"])),
                warn=0.8, crit=0.9,
            )

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

    # -----------------------------------------------------------------------
    # Position
    # -----------------------------------------------------------------------

    def _restore_position(self) -> None:
        """Move the window to its last position if it is still on screen."""
        if not self._config:
            return
        try:
            x, y = (int(v) for v in self._config.get("info_window_pos").split(","))
        except ValueError:
            return
        if get_total_screen_rect().contains(QPoint(x + 20, y + 20)):
            self.move(x, y)

    def _save_position(self) -> None:
        if self._config:
            self._config.set("info_window_pos", f"{self.x()},{self.y()}")

    # -----------------------------------------------------------------------
    # Drag
    # -----------------------------------------------------------------------

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
            self._save_position()
