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

    BUBBLE_COLOR  = QColor(255, 255, 255)
    BORDER_COLOR  = QColor(0, 0, 0)
    TEXT_COLOR    = "blue"
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
        self.label.setStyleSheet(f"""
            QLabel {{
                color: {self.TEXT_COLOR};
                font-size: {self.FONT_SIZE}px;
                background: transparent;
                padding: {self.PADDING}px;
            }}
        """)
        self.label.adjustSize()

        # --- Widget size ---
        w = self.label.width()  + self.PADDING * 2
        h = self.label.height() + self.PADDING * 2
        self.resize(w, h + self.ARROW_HEIGHT)
        self.label.move(self.PADDING, self.PADDING)

    # --- Drawing ---

    def paintEvent(self, event) -> None:
        """Draw the bubble background and arrow."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()

        # Rounded rectangle (bubble body)
        body_rect = QRectF(0, 0, self.width(), self.height() - self.ARROW_HEIGHT)
        path.addRoundedRect(body_rect, self.BORDER_RADIUS, self.BORDER_RADIUS)

        # Downward arrow
        cx = self.width() // 2
        arrow = QPolygonF([
            QPoint(cx - 10, self.height() - self.ARROW_HEIGHT),
            QPoint(cx + 10, self.height() - self.ARROW_HEIGHT),
            QPoint(cx,      self.height() - 2),
        ])
        path.addPolygon(arrow)

        painter.setBrush(self.BUBBLE_COLOR)
        painter.setPen(QPen(self.BORDER_COLOR, self.BORDER_WIDTH))
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
        self.label.adjustSize()

        w = self.label.width()  + self.PADDING * 2
        h = self.label.height() + self.PADDING * 2
        self.resize(w, h + self.ARROW_HEIGHT)
        self.label.move(self.PADDING, self.PADDING)
        self.update()