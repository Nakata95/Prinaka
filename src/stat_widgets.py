"""
stat_widgets.py
---------------
Small widgets shared by the system info windows: usage gauge, history graph,
metric card and network speed row, plus the colours and formatters they use.
"""

from collections import deque

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QPainter, QPainterPath, QColor, QPen


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GREEN  = "#a6e3a1"
YELLOW = "#f9e2af"
RED    = "#f38ba8"
BLUE   = "#89b4fa"
TEAL   = "#94e2d5"
MUTED  = "#6c7086"

HISTORY_LENGTH = 60      # seconds of graph history


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


def latency_color(latency_ms: int) -> str:
    """Colour for a latency in ms (negative means unreachable)."""
    if latency_ms < 0:
        return MUTED
    return GREEN if latency_ms < 60 else YELLOW if latency_ms < 150 else RED


def format_bytes(n: float) -> str:
    """Format a byte count (e.g. '64 GB', '1.8 TB')."""
    gb = n / (1024 ** 3)
    if gb >= 1000:
        return f"{gb / 1024:.1f} TB"
    return f"{gb:.0f} GB" if gb >= 10 else f"{gb:.1f} GB"


def make_label(style: str = "") -> QLabel:
    """Transparent label, optionally with extra stylesheet rules."""
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
        self._title = make_label("color: #cdd6f4; font-size: 12px;")
        self._value = make_label("color: white; font-size: 13px; font-weight: bold;")
        head.addWidget(self._title)
        head.addStretch()
        head.addWidget(self._value)
        layout.addLayout(head)

        self._bar = UsageBar()
        layout.addWidget(self._bar)

        self._detail = make_label(f"color: {MUTED}; font-size: 11px;")
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

        icon = make_label("font-size: 12px;")
        icon.setText(arrow)
        icon.setFixedWidth(18)
        layout.addWidget(icon)

        self._speed = make_label("color: white; font-size: 12px;")
        self._speed.setFixedWidth(88)
        layout.addWidget(self._speed)

        self._spark = Sparkline(color, height=22)
        layout.addWidget(self._spark, 1)

    def update_speed(self, text: str, bps: float) -> None:
        self._speed.setText(text)
        self._spark.push(bps)

    def clear_history(self) -> None:
        self._spark.clear()
