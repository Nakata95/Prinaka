"""
floating.py
-----------
Base class for Prinaka's small always-on-top overlay windows.

Provides dragging that can never lose the window off-screen, a remembered
position, and "bring it back to the middle of the screen" when the saved
position is no longer reachable (monitor unplugged, window dragged away).
"""

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QPoint, QRect


# The top bar must stay this much on screen so the window can always be grabbed
GRAB_WIDTH, GRAB_HEIGHT = 120, 40


class FloatingWindow(QWidget):
    """
    Frameless, translucent, always-on-top window the user can drag around.

    Args:
        config: Optional ConfigManager used to remember the position.
        position_key: Config key holding the position as "x,y".
        flags: Qt window flags (frameless / always on top are the caller's choice).
    """

    def __init__(self, config=None, position_key: str = "", flags=Qt.Window):
        super().__init__(None)
        self._config       = config
        self._position_key = position_key

        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, False)

        self._dragging       = False
        self._drag_start_pos = QPoint()
        self._has_position   = False   # False until restored, moved or centered
        self._center_rect    = None    # area the window is centered on (see center_on)

    # -----------------------------------------------------------------------
    # Position
    # -----------------------------------------------------------------------

    def _restore_position(self) -> None:
        """Move to the saved position if it can still be grabbed there (call once sized)."""
        if not self._config or not self._position_key:
            return
        try:
            x, y = (int(v) for v in self._config.get(self._position_key).split(","))
        except ValueError:
            return
        if self._is_reachable(QPoint(x, y)):
            self.move(x, y)
            self._has_position = True

    def _save_position(self) -> None:
        if self._config and self._position_key:
            self._config.set(self._position_key, f"{self.x()},{self.y()}")

    def _is_reachable(self, pos: QPoint) -> bool:
        """True if the top bar placed at `pos` is visible enough on some screen to be grabbed."""
        bar = QRect(pos.x(), pos.y(), self.width(), GRAB_HEIGHT)
        desktop = QApplication.desktop()
        for i in range(desktop.screenCount()):
            visible = desktop.availableGeometry(i).intersected(bar)
            if visible.width() >= GRAB_WIDTH and visible.height() >= GRAB_HEIGHT:
                return True
        return False

    def _clamp_to_screen(self, pos: QPoint, screen: QRect) -> QPoint:
        """Keep the top bar grabbable on `screen` while dragging."""
        x = max(screen.left() - self.width() + GRAB_WIDTH, min(pos.x(), screen.right() - GRAB_WIDTH))
        y = max(screen.top(), min(pos.y(), screen.bottom() - GRAB_HEIGHT))
        return QPoint(x, y)

    def center_on(self, area: QRect) -> None:
        """Place the window in the middle of `area` (typically a screen's available rect)."""
        self._center_rect  = area
        self._has_position = True
        self._center()

    def _center(self) -> None:
        self.adjustSize()
        area = self._center_rect
        x = area.center().x() - self.width()  // 2
        y = area.center().y() - self.height() // 2
        # never push the top bar out of the area, even if the window is taller than the screen
        self.move(max(area.left(), x), max(area.top(), y))

    def open(self, near=None, activate: bool = True) -> None:
        """
        Show the window, bringing it back to the middle of the screen if its
        position is unknown or can no longer be reached (monitor unplugged,
        dragged away).

        Args:
            near: Widget whose screen is used for centering (e.g. Prinny).
            activate: Give the window focus. Overlays used over a game pass
                False so the game keeps the focus.
        """
        self._center_rect = None
        if not self._has_position or not self._is_reachable(self.pos()):
            desktop = QApplication.desktop()
            screen  = desktop.screenNumber(near) if near is not None else desktop.primaryScreen()
            self.center_on(desktop.availableGeometry(max(screen, 0)))
        self.show()
        self.raise_()
        if activate:
            self.activateWindow()

    # -----------------------------------------------------------------------
    # Drag
    # -----------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging       = True
            self._drag_start_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            desktop = QApplication.desktop()
            screen  = desktop.availableGeometry(desktop.screenNumber(event.globalPos()))
            self.move(self._clamp_to_screen(event.globalPos() - self._drag_start_pos, screen))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging     = False
            self._center_rect  = None   # the user placed it: stop auto-centering
            self._has_position = True
            self._save_position()
