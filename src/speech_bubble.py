"""
speech_bubble.py
----------------
Speech bubble widget for Prinaka.

Displays a rounded popup with a downward arrow above Prinny's head.
Used for random quotes and media notifications.
"""

from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtCore import Qt, QPoint, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath, QPolygonF


# ---------------------------------------------------------------------------
# Speech Bubble
# ---------------------------------------------------------------------------

class SpeechBubble(QWidget):
    """
    A frameless, translucent speech bubble widget.

    Renders a white rounded rectangle with a triangular arrow
    pointing downward toward Prinny's head.

    Args:
        text: The text to display inside the bubble.
        parent: Optional parent widget.
    """

    BUBBLE_COLOR  = QColor(235, 223, 174)
    BORDER_COLOR  = QColor(0, 0, 0)
    TEXT_COLOR    = "black"
    FONT_SIZE     = 20
    PADDING       = 10
    ARROW_HEIGHT  = 15
    BORDER_RADIUS = 12
    BORDER_WIDTH  = 2

    def __init__(self, text: str, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.ToolTip |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # --- Label ---
        self.label = QLabel(text, self)
        self.label.setWordWrap(True)

        self.set_scale(self._scale_from(parent))

    # --- Scaling ---

    @staticmethod
    def _scale_from(prinny_widget) -> float:
        """
        Bubble scale for a Prinny size setting.

        Follows the square root of his size, so the text stays readable when
        he is small and does not become huge when he is big.
        """
        percent = getattr(prinny_widget, "_scale", 100)
        return (percent / 100) ** 0.5

    def set_scale(self, scale: float) -> None:
        """Resize font, padding, arrow and border for a scale (1.0 = base size)."""
        self._padding = round(self.PADDING * scale)
        self._arrow   = round(self.ARROW_HEIGHT * scale)
        self._radius  = round(self.BORDER_RADIUS * scale)
        self._border  = max(1, round(self.BORDER_WIDTH * scale))
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {self.TEXT_COLOR};
                font-size: {round(self.FONT_SIZE * scale)}px;
                background: transparent;
                padding: {self._padding}px;
            }}
        """)
        self._relayout()

    def _relayout(self) -> None:
        """Fit the widget around the label."""
        self.label.adjustSize()
        w = self.label.width()  + self._padding * 2
        h = self.label.height() + self._padding * 2
        self.resize(w, h + self._arrow)
        self.label.move(self._padding, self._padding)
        self.update()

    # --- Drawing ---

    def paintEvent(self, event) -> None:
        """Draw the bubble background and arrow."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()

        # Rounded rectangle (bubble body)
        body_rect = QRectF(0, 0, self.width(), self.height() - self._arrow)
        path.addRoundedRect(body_rect, self._radius, self._radius)

        # Downward arrow
        cx = self.width() // 2
        half = round(10 * self._arrow / self.ARROW_HEIGHT)
        arrow = QPolygonF([
            QPoint(cx - half, self.height() - self._arrow),
            QPoint(cx + half, self.height() - self._arrow),
            QPoint(cx,      self.height() - 2),
        ])
        path.addPolygon(arrow)

        painter.setBrush(self.BUBBLE_COLOR)
        painter.setPen(QPen(self.BORDER_COLOR, self._border))
        painter.drawPath(path)

    # --- Positioning ---

    def update_position(self, prinny_widget) -> None:
        """
        Place the bubble above Prinny's head, keeping it within screen bounds.

        Args:
            prinny_widget: The Prinny QWidget to position relative to.
        """
        if not prinny_widget:
            return

        from PyQt5.QtWidgets import QApplication

        screen    = QApplication.desktop().availableGeometry(prinny_widget)
        center    = prinny_widget.mapToGlobal(prinny_widget.rect().center())

        x = center.x() - self.width()  // 2
        y = center.y() - prinny_widget.height() // 2 - self.height() - 10

        # Keep within horizontal screen bounds
        x = max(screen.left() + 5, min(x, screen.right() - self.width() - 5))

        # If no room above, place below Prinny instead
        if y < screen.top():
            y = center.y() + prinny_widget.height() // 2 + 10

        self.move(x, y)

    def update_text(self, text: str) -> None:
        """
        Update the bubble text and resize accordingly.

        Args:
            text: New text to display.
        """
        self.label.setText(text)
        self._relayout()