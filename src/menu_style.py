"""
menu_style.py
-------------
Shared look of Prinaka's context menus (right-click and tray).

Dark rounded panel using the same palette as the info windows. Call
style_menu() on the top-level menu just before showing it: it also styles
every submenu created so far.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMenu


MENU_STYLE = """
    QMenu {
        background-color: #1e1e2e;
        border: 1px solid #45475a;
        border-radius: 12px;
        padding: 6px;
        color: #cdd6f4;
        font-size: 13px;
    }
    QMenu::item {
        padding: 8px 30px 8px 14px;
        margin: 1px 0;
        border-radius: 7px;
        background: transparent;
    }
    QMenu::item:selected {
        background-color: #45475a;
        color: #ffffff;
    }
    QMenu::item:checked {
        color: #a6e3a1;
    }
    QMenu::item:disabled {
        color: #6c7086;
    }
    QMenu::separator {
        height: 1px;
        background: #313244;
        margin: 5px 10px;
    }
    QMenu::indicator {
        width: 14px;
        height: 14px;
        margin-left: 8px;
        border-radius: 4px;
        border: 1px solid #585b70;
        background: transparent;
    }
    QMenu::indicator:checked {
        background-color: #a6e3a1;
        border: 1px solid #a6e3a1;
    }
    QMenu::right-arrow {
        width: 8px;
        height: 8px;
        margin-right: 8px;
    }
"""


def style_menu(menu: QMenu) -> None:
    """Apply the dark rounded look to a menu and all its submenus."""
    for m in [menu] + menu.findChildren(QMenu):
        # Rounded corners need a translucent frameless window without the
        # native square shadow
        m.setWindowFlags(m.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        m.setAttribute(Qt.WA_TranslucentBackground)
    menu.setStyleSheet(MENU_STYLE)
