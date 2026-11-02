"""
tray.py
-------
System tray icon for Prinaka.

Lets the user show/hide Prinny, open the system info window or quit,
even when Prinny is hidden. A left click toggles his visibility.
"""

import os

from PyQt5.QtWidgets import QSystemTrayIcon, QMenu
from PyQt5.QtGui import QIcon, QPixmap

from menu_style import style_menu
from utils import t, resource_path


ICON_SIZE = 64

# A custom icon dropped in assets/ takes priority over the skin's sprite
CUSTOM_ICONS = ("tray.ico", "tray.png")


class TrayIcon(QSystemTrayIcon):
    """
    Tray icon bound to the Prinny widget.

    Args:
        owner: The Prinny widget (needs toggle_visibility, is_user_hidden,
            current_icon, is_info_window_visible, toggle_info_window,
            is_network_window_visible, toggle_network_window and quit_app).
    """

    def __init__(self, owner):
        super().__init__(owner)
        self._owner = owner

        self.setToolTip("Prinaka")
        self.activated.connect(self._on_activated)

        self._menu = QMenu()
        style_menu(self._menu)
        self._menu.aboutToShow.connect(self._rebuild_menu)
        self.setContextMenu(self._menu)

        self.refresh_icon()

    def refresh_icon(self) -> None:
        """Use assets/tray.ico (or tray.png) if present, else the skin's first idle frame."""
        for name in CUSTOM_ICONS:
            path = resource_path(os.path.join("assets", name))
            icon = QIcon(path) if os.path.exists(path) else QIcon()
            if not icon.isNull():
                self.setIcon(icon)
                return

        pixmap: QPixmap = self._owner.current_icon()
        if pixmap and not pixmap.isNull():
            self.setIcon(QIcon(pixmap.scaled(ICON_SIZE, ICON_SIZE)))

    def _rebuild_menu(self) -> None:
        """Rebuild the menu each time so labels follow the language and state."""
        self._menu.clear()

        toggle_key = "tray_show" if self._owner.is_user_hidden() else "tray_hide"
        self._menu.addAction(t(toggle_key), self._owner.toggle_visibility)
        info_key = "menu_sys_info_close" if self._owner.is_info_window_visible() else "menu_sys_info"
        self._menu.addAction(t(info_key), self._owner.toggle_info_window)
        net_key = "menu_net_close" if self._owner.is_network_window_visible() else "menu_net"
        self._menu.addAction(t(net_key), self._owner.toggle_network_window)
        player_key = "menu_player_close" if self._owner.is_player_window_visible() else "menu_player"
        self._menu.addAction(t(player_key), self._owner.toggle_player_window)
        self._menu.addSeparator()
        self._menu.addAction(t("menu_quit"), self._owner.quit_app)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:   # left click
            self._owner.toggle_visibility()
