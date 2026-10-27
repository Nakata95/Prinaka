"""
presence_window.py
------------------
Rich Presence manager window for Prinaka.

Left panel   : list of saved profiles (icon, name, details)
Center panel : tabbed form (general / images / buttons) + action buttons
Right panel  : live preview of what Discord will display (can be hidden)

Also provides PreviewPopup, a small standalone window showing the preview
of one profile (used by the right-click menu).

Profiles are stored in assets/presences.json.
"""

import json
import threading
import time
import urllib.request

from PyQt5.QtWidgets import (
    QSizePolicy, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QCheckBox, QPushButton, QListWidget, QListWidgetItem, QTabWidget,
    QFrame, QMessageBox, QShortcut
)
from PyQt5.QtCore import Qt, QSize, QRectF, QObject, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QPixmap, QImage, QColor, QPainter, QPainterPath, QFont, QKeySequence
)

from utils import t
from config import ConfigManager
from discord_presence import (
    DiscordPresenceManager, STATUS_TEXTS,
    load_profiles, save_profiles, unique_name, validate_profile,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ICON_SIZE        = 40   # px, icon size in the list
PREVIEW_WIDTH    = 320  # px, width of the preview card
PREVIEW_IMG_SIZE = 76   # px, large image in the preview card
PREVIEW_SMALL    = 26   # px, small image overlay in the preview card
PREVIEW_DELAY_MS = 400  # debounce before refreshing the preview

MAX_TEXT_LENGTH  = 128  # Discord limit for details / state / tooltips
MAX_LABEL_LENGTH = 32   # Discord limit for button labels

STYLE = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-size: 13px;
}
QLabel { background: transparent; }
QLineEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 5px 8px;
    color: #cdd6f4;
}
QLineEdit:focus { border: 1px solid #89b4fa; }
QListWidget {
    background-color: #181825;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 2px;
    outline: none;
}
QListWidget::item { padding: 2px 4px; border-radius: 6px; }
QListWidget::item:selected { background-color: #45475a; }
QListWidget::item:hover { background-color: #313244; }
QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    padding: 7px 18px;
    border: 1px solid #45475a;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected { background-color: #313244; color: #cdd6f4; }
QTabBar::tab:hover:!selected { background-color: #232334; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #45475a;
    border-radius: 3px;
    background: #313244;
}
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
QPushButton {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 7px 14px;
    color: #cdd6f4;
}
QPushButton:hover { background-color: #45475a; }
QPushButton:disabled { color: #6c7086; background-color: #232334; }
QPushButton:checked { background-color: #45475a; border-color: #89b4fa; }
QPushButton#btn_activate {
    background-color: #a6e3a1;
    color: #1e1e2e; font-weight: bold; border: none;
}
QPushButton#btn_activate:hover { background-color: #94e2d5; }
QPushButton#btn_activate:disabled { background-color: #3b4a3b; color: #6c7086; }
QPushButton#btn_stop {
    background-color: #f38ba8;
    color: #1e1e2e; font-weight: bold; border: none;
}
QPushButton#btn_stop:hover { background-color: #eba0ac; }
QPushButton#btn_stop:disabled { background-color: #4a3038; color: #6c7086; }
QPushButton#btn_delete {
    background-color: transparent;
    border: 1px solid #f38ba8;
    color: #f38ba8;
}
QPushButton#btn_delete:hover { background-color: #f38ba820; }
QPushButton#btn_delete:disabled { border-color: #4a3038; color: #6c7086; }
QLabel#section {
    color: #6c7086; font-size: 11px;
    padding: 2px 0px 2px 2px;
}
QLabel#hint {
    color: #6c7086; font-size: 11px;
    font-style: italic;
}
QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 4px;
}
QFrame#preview {
    background-color: #111214;
    border: 1px solid #2b2d31;
    border-radius: 10px;
}
QLabel#preview_header {
    color: #b5bac1; font-size: 11px; font-weight: bold;
}
QLabel#preview_title { color: #f2f3f5; font-weight: bold; font-size: 14px; }
QLabel#preview_line  { color: #dbdee1; font-size: 12px; }
QLabel#preview_timer { color: #b5bac1; font-size: 12px; }
QLabel#preview_btn {
    background-color: #4e5058;
    border-radius: 4px;
    padding: 7px 8px;
    color: #ffffff;
    font-size: 12px;
    font-weight: bold;
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_placeholder_icon(size: int = ICON_SIZE, radius: int = 6) -> QPixmap:
    """
    Create a rounded grey square with a '!' as fallback icon.

    Args:
        size: Size in pixels.
        radius: Corner radius in pixels.

    Returns:
        QPixmap of the placeholder icon.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#313244"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#6c7086"))
    font = QFont()
    font.setPixelSize(int(size * 0.55))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "!")
    painter.end()
    return _rounded(pixmap, radius)


def _rounded(pixmap: QPixmap, radius: float) -> QPixmap:
    """Return `pixmap` with rounded corners (a stylesheet radius does not clip pixmaps)."""
    out = QPixmap(pixmap.size())
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(out.rect()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return out


def _cover(image: QImage, size: int, radius: float = 6) -> QPixmap:
    """Scale an image to fill a size x size rounded square."""
    pixmap = QPixmap.fromImage(image).scaled(
        size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
    )
    # KeepAspectRatioByExpanding can overflow on one axis: crop to the square
    x = (pixmap.width()  - size) // 2
    y = (pixmap.height() - size) // 2
    return _rounded(pixmap.copy(x, y, size, size), radius)


def _is_client_id(text: str) -> bool:
    """Discord application IDs are numeric snowflakes (17-20 digits)."""
    return text.isdigit() and 17 <= len(text) <= 20


def _is_url(text: str) -> bool:
    return text.lower().startswith(("http://", "https://"))


def _format_elapsed(seconds: float) -> str:
    """Format seconds as mm:ss, or h:mm:ss past one hour (Discord style)."""
    hours, rest = divmod(max(0, int(seconds)), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class ImageFetcher(QObject):
    """
    Downloads images in background threads and caches them.

    `loaded(url, image)` is emitted once per request; the image is null
    on failure. QImage (not QPixmap) is used because QPixmap must only
    be created on the GUI thread.
    """

    loaded = pyqtSignal(str, QImage)

    def __init__(self):
        super().__init__()
        self._cache:   dict = {}
        self._pending: set  = set()

    def request(self, url: str) -> None:
        if url in self._cache:
            self.loaded.emit(url, self._cache[url])
        elif url not in self._pending:
            self._pending.add(url)
            threading.Thread(target=self._run, args=(url,), daemon=True).start()

    def _run(self, url: str) -> None:
        image = QImage()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Prinaka/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                image.loadFromData(resp.read())
        except Exception:
            pass
        self._cache[url] = image
        self._pending.discard(url)
        self.loaded.emit(url, image)


class AppInfoFetcher(QObject):
    """
    Looks up a Discord application (name + icon) from its Client ID.

    Uses Discord's public endpoint, so no token is needed. This is what
    Discord itself shows as the activity name and fallback image.

    `loaded(client_id, name, icon_url)` is emitted once per lookup;
    `name` is empty if the application could not be found.
    """

    loaded = pyqtSignal(str, str, str)

    def __init__(self):
        super().__init__()
        self._cache:   dict = {}
        self._pending: set  = set()

    def cached(self, client_id: str) -> tuple[str, str] | None:
        """Return (name, icon_url) if already looked up, else None."""
        return self._cache.get(client_id)

    def request(self, client_id: str) -> None:
        if client_id in self._cache:
            name, icon = self._cache[client_id]
            self.loaded.emit(client_id, name, icon)
        elif client_id not in self._pending:
            self._pending.add(client_id)
            threading.Thread(target=self._run, args=(client_id,), daemon=True).start()

    def _run(self, client_id: str) -> None:
        name, icon_url = "", ""
        try:
            req = urllib.request.Request(
                f"https://discord.com/api/v10/applications/{client_id}/rpc",
                headers={"User-Agent": "DiscordBot (https://github.com/Nakata95/Prinaka, 1.0)"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            name = data.get("name") or ""
            if data.get("icon"):
                icon_url = f"https://cdn.discordapp.com/app-icons/{client_id}/{data['icon']}.png?size=256"
        except Exception:
            pass
        if name:   # do not cache failures: the user may fix a typo and retry
            self._cache[client_id] = (name, icon_url)
        self._pending.discard(client_id)
        self.loaded.emit(client_id, name, icon_url)


_fetcher: ImageFetcher | None = None
_app_fetcher: AppInfoFetcher | None = None


def get_fetcher() -> ImageFetcher:
    """Return the shared ImageFetcher (created on first use, on the GUI thread)."""
    global _fetcher
    if _fetcher is None:
        _fetcher = ImageFetcher()
    return _fetcher


def get_app_fetcher() -> AppInfoFetcher:
    """Return the shared AppInfoFetcher (created on first use, on the GUI thread)."""
    global _app_fetcher
    if _app_fetcher is None:
        _app_fetcher = AppInfoFetcher()
    return _app_fetcher


# ---------------------------------------------------------------------------
# Profile list item widget
# ---------------------------------------------------------------------------

class ProfileItemWidget(QWidget):
    """
    List item showing an icon, the profile name and its details line.

    The icon is loaded asynchronously from the large_image URL and falls
    back to a grey '!' placeholder. A green dot marks the profile
    currently shown on Discord.
    """

    def __init__(self, profile: dict, active: bool = False, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        self._icon_label.setPixmap(_make_placeholder_icon())
        layout.addWidget(self._icon_label)

        texts = QVBoxLayout()
        texts.setSpacing(0)
        name_label = QLabel(("🟢 " if active else "") + (profile.get("name") or "—"))
        name_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        texts.addWidget(name_label)

        subtitle = profile.get("details") or profile.get("state") or ""
        sub_label = QLabel(subtitle)
        sub_label.setStyleSheet("color: #6c7086; font-size: 11px;")
        sub_label.setVisible(bool(subtitle))
        texts.addWidget(sub_label)

        layout.addLayout(texts, 1)

        self._url = profile.get("large_image", "").strip()
        if _is_url(self._url):
            fetcher = get_fetcher()
            fetcher.loaded.connect(self._on_icon_loaded)
            fetcher.request(self._url)

    def _on_icon_loaded(self, url: str, image: QImage) -> None:
        if url == self._url and not image.isNull():
            self._icon_label.setPixmap(_cover(image, ICON_SIZE))


# ---------------------------------------------------------------------------
# Preview card
# ---------------------------------------------------------------------------

class PreviewCard(QFrame):
    """Reproduction of the 'Playing' card Discord shows in a user profile."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("preview")
        self.setFixedWidth(PREVIEW_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)

        self._large_url = ""    # image actually displayed (profile's, or the app icon)
        self._small_url = ""
        self._client_id = ""
        self._app_name  = ""
        self._app_icon  = ""
        self._own_large = ""    # large image set in the profile
        self._timer_on  = False
        self._start     = time.time()   # simulated start when no real one is known

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        header = QLabel(t("presence_preview_header"))
        header.setObjectName("preview_header")
        root.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(12)

        self._large = QLabel()
        self._large.setFixedSize(PREVIEW_IMG_SIZE, PREVIEW_IMG_SIZE)
        self._small = QLabel(self._large)
        badge = PREVIEW_SMALL + 6
        self._small.setFixedSize(badge, badge)
        self._small.setAlignment(Qt.AlignCenter)
        self._small.move(PREVIEW_IMG_SIZE - badge + 6, PREVIEW_IMG_SIZE - badge + 6)
        self._small.setStyleSheet(f"background-color: #111214; border-radius: {badge // 2}px;")
        self._small.hide()
        body.addWidget(self._large, 0, Qt.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        self._app     = QLabel()
        self._app.setObjectName("preview_title")
        self._details = QLabel()
        self._details.setObjectName("preview_line")
        self._state   = QLabel()
        self._state.setObjectName("preview_line")
        self._clock   = QLabel()
        self._clock.setObjectName("preview_timer")
        for w in (self._app, self._details, self._state, self._clock):
            w.setWordWrap(True)
            texts.addWidget(w)
        body.addLayout(texts, 1)
        root.addLayout(body)

        self._btn1 = QLabel()
        self._btn2 = QLabel()
        for btn in (self._btn1, self._btn2):
            btn.setObjectName("preview_btn")
            btn.setAlignment(Qt.AlignCenter)
            btn.setFixedHeight(32)
            root.addWidget(btn)

        get_fetcher().loaded.connect(self._on_image_loaded)
        get_app_fetcher().loaded.connect(self._on_app_loaded)

        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._tick)
        self._ticker.start(1000)

    def reset_clock(self) -> None:
        """Restart the simulated elapsed-time counter."""
        self._start = time.time()
        self._tick()

    def show_profile(self, p: dict, start: float | None = None) -> None:
        """
        Refresh the card from a profile dict.

        Args:
            p: Profile dict.
            start: Real start timestamp if the profile is live on Discord,
                otherwise the simulated one is used.
        """
        self._client_id = p.get("client_id", "").strip()
        self._app_name, self._app_icon = "", ""
        if _is_client_id(self._client_id):
            info = get_app_fetcher().cached(self._client_id)
            if info:
                self._app_name, self._app_icon = info
            else:
                get_app_fetcher().request(self._client_id)
        self._app.setText(self._app_name or p.get("app_name") or t("presence_preview_app"))

        for label, key in ((self._details, "details"), (self._state, "state")):
            text = p.get(key, "")
            label.setText(text)
            label.setVisible(bool(text))

        self._timer_on = bool(p.get("show_timer"))
        if start:
            self._start = start
        self._clock.setVisible(self._timer_on)
        self._tick()

        for i, btn in ((1, self._btn1), (2, self._btn2)):
            label = p.get(f"button{i}_label", "")
            btn.setText(label)
            btn.setVisible(bool(label))

        self._own_large = p.get("large_image", "").strip()
        self._small_url = p.get("small_image", "").strip()
        self._apply_images()

    def _apply_images(self) -> None:
        """Show the profile's large image, or the app icon like Discord does."""
        self._large_url = self._own_large if _is_url(self._own_large) else self._app_icon
        self._large.setPixmap(_make_placeholder_icon(PREVIEW_IMG_SIZE, 10))
        self._small.hide()
        for url in (self._large_url, self._small_url):
            if _is_url(url):
                get_fetcher().request(url)

    def _on_app_loaded(self, client_id: str, name: str, icon_url: str) -> None:
        if client_id != self._client_id or not name:
            return
        self._app_name, self._app_icon = name, icon_url
        self._app.setText(name)
        self._apply_images()

    def _tick(self) -> None:
        if self._timer_on:
            self._clock.setText(
                f"{_format_elapsed(time.time() - self._start)} {t('presence_elapsed')}"
            )

    def _on_image_loaded(self, url: str, image: QImage) -> None:
        if image.isNull():
            return
        if url == self._large_url:
            self._large.setPixmap(_cover(image, PREVIEW_IMG_SIZE, 10))
        if url == self._small_url:
            self._small.setPixmap(_cover(image, PREVIEW_SMALL, PREVIEW_SMALL / 2))
            self._small.show()


class PreviewPopup(QWidget):
    """Small always-on-top window showing the Discord preview of one profile."""

    def __init__(self, manager: DiscordPresenceManager):
        super().__init__(None)
        self._manager = manager

        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        self._card = PreviewCard()
        layout.addWidget(self._card)

        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close)

    def set_profile(self, profile: dict) -> None:
        """Show `profile`; uses the real start time if it is live on Discord."""
        m = self._manager
        live = m.is_active and m.profile_name == profile.get("name")
        self.setWindowTitle(t("presence_preview_title").format(name=profile.get("name", "")))
        self._card.reset_clock()
        self._card.show_profile(profile, start=m.start_time if live else None)


# ---------------------------------------------------------------------------
# Presence Window
# ---------------------------------------------------------------------------

class PresenceWindow(QWidget):
    """Discord Rich Presence manager window."""

    def __init__(self, presence_manager: DiscordPresenceManager):
        super().__init__(None)

        self._manager       = presence_manager
        self._config        = ConfigManager()
        self._profiles      = load_profiles()
        self._editing_index = -1
        self._connecting    = False
        self._snapshot      = {}

        self.setWindowTitle(t("presence_title"))
        self.setMinimumSize(1080, 660)
        self.setStyleSheet(STYLE)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._refresh_preview)

        self._build_ui()
        self._refresh_list()
        self._fill_form({})
        self._refresh_state()

        QShortcut(QKeySequence.Save, self, activated=self._save_profile)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._activate)

        self._manager.state_changed.connect(self._on_manager_state)
        get_app_fetcher().loaded.connect(self._on_app_info)

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(14)

        # ── Left: profile list ───────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(6)

        self._list = QListWidget()
        self._list.setFixedWidth(230)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._list.currentRowChanged.connect(self._on_select)
        left.addWidget(self._list)

        btn_new = QPushButton(t("presence_btn_new"))
        btn_new.clicked.connect(self._new_profile)
        left.addWidget(btn_new)

        self._btn_duplicate = QPushButton(t("presence_btn_duplicate"))
        self._btn_duplicate.clicked.connect(self._duplicate_profile)
        left.addWidget(self._btn_duplicate)

        self._btn_delete = QPushButton(t("presence_btn_delete"))
        self._btn_delete.setObjectName("btn_delete")
        self._btn_delete.clicked.connect(self._delete_profile)
        left.addWidget(self._btn_delete)

        root.addLayout(left)

        # ── Center: state bar, tabs, actions ─────────────────────────────
        center = QVBoxLayout()
        center.setSpacing(10)

        top = QHBoxLayout()
        self._state_label = QLabel()
        top.addWidget(self._state_label, 1)

        self._btn_preview = QPushButton(t("presence_btn_preview"))
        self._btn_preview.setCheckable(True)
        self._btn_preview.setChecked(self._config.get("presence_preview_visible"))
        self._btn_preview.toggled.connect(self._toggle_preview)
        top.addWidget(self._btn_preview)
        center.addLayout(top)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), t("presence_tab_general"))
        tabs.addTab(self._build_images_tab(),  t("presence_tab_images"))
        tabs.addTab(self._build_buttons_tab(), t("presence_tab_buttons"))
        center.addWidget(tabs, 1)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(18)
        center.addWidget(self._status)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        self._btn_save = QPushButton(t("presence_btn_save"))
        self._btn_save.setToolTip("Ctrl+S")
        self._btn_save.clicked.connect(self._save_profile)
        actions.addWidget(self._btn_save)

        self._btn_activate = QPushButton(t("presence_btn_activate"))
        self._btn_activate.setObjectName("btn_activate")
        self._btn_activate.setToolTip("Ctrl+Enter")
        self._btn_activate.clicked.connect(self._activate)
        actions.addWidget(self._btn_activate, 1)

        self._btn_stop = QPushButton(t("presence_btn_stop"))
        self._btn_stop.setObjectName("btn_stop")
        self._btn_stop.clicked.connect(self._stop)
        actions.addWidget(self._btn_stop)

        center.addLayout(actions)
        root.addLayout(center, 1)

        # ── Right: preview panel ─────────────────────────────────────────
        self._preview_panel = QWidget()
        panel = QVBoxLayout(self._preview_panel)
        panel.setContentsMargins(0, 0, 0, 0)
        panel.setSpacing(8)

        title = QLabel(t("presence_preview"))
        title.setObjectName("section")
        panel.addWidget(title)

        self._preview = PreviewCard()
        panel.addWidget(self._preview)

        self._warn = QLabel()
        self._warn.setWordWrap(True)
        self._warn.setFixedWidth(PREVIEW_WIDTH)
        self._warn.setStyleSheet("color: #f9e2af; font-size: 12px;")
        panel.addWidget(self._warn)
        panel.addStretch()

        root.addWidget(self._preview_panel)
        self._preview_panel.setVisible(self._btn_preview.isChecked())

    def _make_form_tab(self) -> tuple[QWidget, QFormLayout]:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        return page, form

    def _field(self, placeholder: str = "", max_length: int = 0) -> QLineEdit:
        w = QLineEdit()
        w.setPlaceholderText(placeholder)
        if max_length:
            w.setMaxLength(max_length)
        w.textChanged.connect(self._on_edited)
        return w

    def _add_row(self, form: QFormLayout, label_key: str, widget: QWidget,
                 hint_key: str = None, inline_hint: bool = False) -> None:
        """Add a labelled row; the hint is a tooltip (and optionally shown inline)."""
        label = QLabel(t(label_key))
        if hint_key:
            label.setToolTip(t(hint_key))
            widget.setToolTip(t(hint_key))
        form.addRow(label, widget)
        if hint_key and inline_hint:
            hint = QLabel(t(hint_key))
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            form.addRow("", hint)

    def _build_general_tab(self) -> QWidget:
        page, form = self._make_form_tab()

        self._f_profile_name = self._field(max_length=MAX_LABEL_LENGTH)
        self._add_row(form, "presence_profile_name", self._f_profile_name, "presence_profile_name_hint")

        self._f_client_id = self._field("123456789012345678")
        self._add_row(form, "presence_client_id", self._f_client_id, "presence_client_id_hint", inline_hint=True)

        self._f_app_name = self._field(t("presence_app_name_auto"))
        self._f_app_name.setReadOnly(True)   # filled from the Client ID, see _on_app_info
        self._add_row(form, "presence_app_name", self._f_app_name, "presence_app_name_hint")

        self._f_details = self._field(max_length=MAX_TEXT_LENGTH)
        self._add_row(form, "presence_details", self._f_details, "presence_details_hint")

        self._f_state = self._field(max_length=MAX_TEXT_LENGTH)
        self._add_row(form, "presence_state", self._f_state, "presence_state_hint")

        self._f_timer = QCheckBox(t("presence_show_timer"))
        self._f_timer.toggled.connect(self._on_edited)
        form.addRow("", self._f_timer)

        return page

    def _build_images_tab(self) -> QWidget:
        page, form = self._make_form_tab()

        self._f_large_image = self._field("https://...")
        self._add_row(form, "presence_large_image", self._f_large_image, "presence_large_image_hint")

        self._f_large_text = self._field(max_length=MAX_TEXT_LENGTH)
        self._add_row(form, "presence_large_text", self._f_large_text, "presence_large_text_hint")

        self._f_small_image = self._field("https://...")
        self._add_row(form, "presence_small_image", self._f_small_image, "presence_small_image_hint")

        self._f_small_text = self._field(max_length=MAX_TEXT_LENGTH)
        self._add_row(form, "presence_small_text", self._f_small_text, "presence_small_text_hint")

        return page

    def _build_buttons_tab(self) -> QWidget:
        page, form = self._make_form_tab()

        self._f_btn1_label = self._field("My GitHub", MAX_LABEL_LENGTH)
        self._add_row(form, "presence_button1_label", self._f_btn1_label)

        self._f_btn1_url = self._field("https://github.com/...")
        self._add_row(form, "presence_button1_url", self._f_btn1_url)

        self._f_btn2_label = self._field(max_length=MAX_LABEL_LENGTH)
        self._add_row(form, "presence_button2_label", self._f_btn2_label)

        self._f_btn2_url = self._field()
        self._add_row(form, "presence_button2_url", self._f_btn2_url)

        return page

    def _toggle_preview(self, visible: bool) -> None:
        self._preview_panel.setVisible(visible)
        self._config.set("presence_preview_visible", visible)

    # -----------------------------------------------------------------------
    # Profile list
    # -----------------------------------------------------------------------

    def _refresh_list(self) -> None:
        """Rebuild the list with custom item widgets."""
        self._list.blockSignals(True)
        self._list.clear()

        active_name = self._manager.profile_name if self._manager.is_active else None
        for profile in self._profiles:
            item   = QListWidgetItem(self._list)
            widget = ProfileItemWidget(profile, active=profile.get("name") == active_name)
            item.setSizeHint(widget.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)

        self._list.blockSignals(False)

        has_selection = 0 <= self._editing_index < len(self._profiles)
        if has_selection:
            self._list.setCurrentRow(self._editing_index)
        self._btn_delete.setEnabled(has_selection)
        self._btn_duplicate.setEnabled(has_selection)

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._profiles):
            return
        self._editing_index = row
        self._fill_form(self._profiles[row])
        self._btn_delete.setEnabled(True)
        self._btn_duplicate.setEnabled(True)
        self._set_status("")

    # -----------------------------------------------------------------------
    # Form
    # -----------------------------------------------------------------------

    def _fill_form(self, p: dict) -> None:
        self._f_profile_name.setText(p.get("name",          ""))
        self._f_client_id.setText(   p.get("client_id",     ""))
        self._f_app_name.setText(    p.get("app_name",       ""))
        self._f_details.setText(     p.get("details",        ""))
        self._f_state.setText(       p.get("state",          ""))
        self._f_large_image.setText( p.get("large_image",    ""))
        self._f_large_text.setText(  p.get("large_text",     ""))
        self._f_small_image.setText( p.get("small_image",    ""))
        self._f_small_text.setText(  p.get("small_text",     ""))
        self._f_btn1_label.setText(  p.get("button1_label",  ""))
        self._f_btn1_url.setText(    p.get("button1_url",    ""))
        self._f_btn2_label.setText(  p.get("button2_label",  ""))
        self._f_btn2_url.setText(    p.get("button2_url",    ""))
        self._f_timer.setChecked(    p.get("show_timer",    False))
        self._mark_clean()
        self._refresh_preview()

    def _read_form(self) -> dict:
        return {
            "name":          self._f_profile_name.text().strip() or "Profile",
            "client_id":     self._f_client_id.text().strip(),
            "app_name":      self._f_app_name.text().strip(),
            "details":       self._f_details.text().strip(),
            "state":         self._f_state.text().strip(),
            "large_image":   self._f_large_image.text().strip(),
            "large_text":    self._f_large_text.text().strip(),
            "small_image":   self._f_small_image.text().strip(),
            "small_text":    self._f_small_text.text().strip(),
            "button1_label": self._f_btn1_label.text().strip(),
            "button1_url":   self._f_btn1_url.text().strip(),
            "button2_label": self._f_btn2_label.text().strip(),
            "button2_url":   self._f_btn2_url.text().strip(),
            "show_timer":    self._f_timer.isChecked(),
        }

    def _mark_clean(self) -> None:
        """Remember the current form content as the saved state."""
        self._snapshot = self._read_form()
        self._update_dirty()

    def _update_dirty(self) -> None:
        """Enable Save and show a dot in the title only when the form changed."""
        dirty = self._read_form() != self._snapshot
        self._btn_save.setEnabled(dirty)
        self.setWindowTitle(t("presence_title") + (" •" if dirty else ""))

    def _on_edited(self, *_) -> None:
        self._update_dirty()
        self._preview_timer.start(PREVIEW_DELAY_MS)

    def _format_problem(self, problem: tuple) -> str:
        key, args = problem
        args = dict(args)
        if "field" in args:
            args["field"] = t(f"presence_{args['field']}")
        return t(key).format(**args)

    def _set_app_name(self, name: str) -> None:
        """Fill the read-only app name without counting it as a user edit."""
        self._f_app_name.setText(name)
        self._snapshot["app_name"] = name
        self._update_dirty()

    def _on_app_info(self, client_id: str, name: str, icon_url: str) -> None:
        """Slot for AppInfoFetcher.loaded: show the app Discord links to this Client ID."""
        if client_id != self._f_client_id.text().strip():
            return   # the user kept typing, stale answer
        self._set_app_name(name)
        self._warn.setText("" if name else t("presence_app_not_found"))

    def _refresh_preview(self) -> None:
        profile = self._read_form()
        cid = profile["client_id"]
        if not _is_client_id(cid):
            self._set_app_name("")
            profile["app_name"] = ""
        else:
            info = get_app_fetcher().cached(cid)
            if info:   # already looked up: no signal will come, apply it now
                self._set_app_name(info[0])
                profile["app_name"] = info[0]
        m = self._manager
        live = m.is_active and m.profile_name == profile["name"]
        self._preview.show_profile(profile, start=m.start_time if live else None)

        problem = validate_profile(profile)
        if problem:
            self._warn.setText(self._format_problem(problem))
        elif not cid:
            self._warn.setText(t("presence_no_client_id"))
        elif not _is_client_id(cid):
            self._warn.setText(t("presence_bad_client_id"))
        else:
            self._warn.setText("")

    # -----------------------------------------------------------------------
    # Profile actions
    # -----------------------------------------------------------------------

    def _new_profile(self) -> None:
        self._editing_index = -1
        self._list.clearSelection()
        self._fill_form({})
        self._btn_delete.setEnabled(False)
        self._btn_duplicate.setEnabled(False)
        self._f_profile_name.setFocus()
        self._set_status("")

    def _store(self, profile: dict) -> None:
        """Insert or update `profile` at the editing index, with a unique name."""
        profile["name"] = unique_name(profile["name"], self._profiles, self._editing_index)

        if 0 <= self._editing_index < len(self._profiles):
            self._profiles[self._editing_index] = profile
        else:
            self._profiles.append(profile)
            self._editing_index = len(self._profiles) - 1

        save_profiles(self._profiles)
        self._refresh_list()
        self._f_profile_name.setText(profile["name"])
        self._mark_clean()

    def _save_profile(self) -> None:
        if not self._btn_save.isEnabled():
            return
        self._store(self._read_form())
        self._set_status(t("presence_saved"), success=True)

    def _duplicate_profile(self) -> None:
        if not 0 <= self._editing_index < len(self._profiles):
            return
        self._editing_index = -1   # store the form content as a new entry
        self._store(self._read_form())
        self._set_status(t("presence_saved"), success=True)

    def _delete_profile(self) -> None:
        if not 0 <= self._editing_index < len(self._profiles):
            return
        name = self._profiles[self._editing_index].get("name", "")
        answer = QMessageBox.question(
            self, t("presence_title"), t("presence_confirm_delete").format(name=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        self._profiles.pop(self._editing_index)
        save_profiles(self._profiles)
        self._editing_index = -1
        self._refresh_list()
        self._fill_form({})
        self._set_status(t("presence_deleted"), success=True)

    # -----------------------------------------------------------------------
    # Presence actions
    # -----------------------------------------------------------------------

    def _activate(self) -> None:
        if self._connecting:
            return
        profile = self._read_form()

        if not profile["client_id"]:
            self._set_status(t("presence_no_client_id"), success=False)
            return

        problem = validate_profile(profile)
        if problem:
            self._set_status(self._format_problem(problem), success=False)
            return

        self._store(profile)   # activate what is saved, so autostart can find it
        self._connecting = True
        self._refresh_state()
        self._set_status(t("presence_connecting"), success=True)
        self._manager.activate_async(self._profiles[self._editing_index])

    def _stop(self) -> None:
        self._manager.stop()

    def _on_manager_state(self, active: bool, message: str) -> None:
        """Slot for DiscordPresenceManager.state_changed (runs on the GUI thread)."""
        self._connecting = False
        self._refresh_state()
        self._refresh_list()
        self._refresh_preview()   # picks up the real start time

        if message in STATUS_TEXTS:
            key, success = STATUS_TEXTS[message]
            self._set_status(t(key), success=success)
        else:
            self._set_status(t("presence_error").format(error=message), success=False)

    def _refresh_state(self) -> None:
        """Update the state line and enable/disable the action buttons."""
        m = self._manager
        if self._connecting:
            text, color = t("presence_state_connecting"), "#f9e2af"
        elif m.is_active:
            text, color = t("presence_state_active").format(name=m.profile_name), "#a6e3a1"
        elif m.is_waiting:
            text, color = t("presence_state_waiting"), "#f9e2af"
        else:
            text, color = t("presence_state_idle"), "#6c7086"

        self._state_label.setText(text)
        self._state_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color};")
        self._btn_activate.setEnabled(not self._connecting)
        self._btn_stop.setEnabled(m.is_active or m.is_waiting)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_state()
        self._refresh_list()

    def _set_status(self, text: str, success: bool = True) -> None:
        color = "#a6e3a1" if success else "#f38ba8"
        self._status.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._status.setText(text)
