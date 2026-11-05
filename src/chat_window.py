"""
chat_window.py
--------------
Chat window to talk to Prinny (local AI, see ai.py).

Unlike the overlays it takes the keyboard focus, since you type in it. Enter
sends the message; the answer appears as soon as the model has written it.
"""

import html
import threading

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QTextBrowser
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent

import safe_commands
from floating import FloatingWindow
from ai_tools import SEARCH_TOOL, looks_like_order, select_tools
from stat_widgets import BLUE, GREEN, MUTED, make_label
from utils import t


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_SIZE = (430, 500)
USER_COLOR  = BLUE
PRINNY_COLOR = GREEN


class ChatWindow(FloatingWindow):
    """
    Conversation window.

    Args:
        config: ConfigManager (remembers the position).
        session: ai.ChatSession answering the messages.
        build_prompt: Callable returning the system prompt (called per message,
            so it carries the current state of Prinny).
    """

    _command_done = pyqtSignal(str, str)       # (what was run, its output) from the worker thread

    STYLE_CONTAINER = """
        QFrame#container {
            background: rgba(24, 24, 37, 240);
            border: 1px solid rgba(255, 255, 255, 30);
            border-radius: 12px;
        }
    """
    STYLE_BUTTON = (
        "QPushButton { color: #a6adc8; background: transparent; border: none; font-size: 16px; }"
        "QPushButton:hover { color: white; }"
        "QPushButton:disabled { color: #45475a; }"
    )
    STYLE_VIEW = (
        "QTextBrowser { background: transparent; border: none; color: #cdd6f4; font-size: 14px; }"
        "QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }"
        "QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; min-height: 30px; }"
        "QScrollBar::handle:vertical:hover { background: #585b70; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
    )
    STYLE_INPUT = (
        "QLineEdit { background: rgba(255, 255, 255, 18); color: #cdd6f4; border: 1px solid #45475a;"
        " border-radius: 8px; padding: 7px 10px; font-size: 14px; }"
        "QLineEdit:focus { border-color: #89b4fa; }"
        "QLineEdit:disabled { color: #6c7086; }"
    )

    def __init__(self, config, session, build_prompt):
        super().__init__(config, "chat_window_pos", Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(*WINDOW_SIZE)
        self._session      = session
        self._build_prompt = build_prompt
        self._waiting      = False

        self._build_ui()
        session.reply.connect(self._on_reply)
        session.failed.connect(self._on_failed)
        session.acted.connect(self._on_acted)
        self._command_done.connect(self._on_command_done)

        self._restore_position()
        self._show_welcome()

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        container = QFrame(self)
        container.setObjectName("container")
        container.setStyleSheet(self.STYLE_CONTAINER)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        body = QVBoxLayout(container)
        body.setContentsMargins(16, 12, 12, 14)
        body.setSpacing(10)

        top = QHBoxLayout()
        title = make_label("color: #cdd6f4; font-size: 16px; font-weight: bold;")
        title.setText(t("chat_title"))
        top.addWidget(title)
        top.addStretch()
        self._clear_btn = QPushButton("🗑")
        self._clear_btn.setFixedSize(28, 28)
        self._clear_btn.setStyleSheet(self.STYLE_BUTTON)
        self._clear_btn.setToolTip(t("chat_clear"))
        self._clear_btn.clicked.connect(self._clear)
        close_btn = QPushButton("✖")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(self.STYLE_BUTTON)
        close_btn.clicked.connect(self.hide)
        top.addWidget(self._clear_btn)
        top.addWidget(close_btn)
        body.addLayout(top)

        self._view = QTextBrowser()
        self._view.setStyleSheet(self.STYLE_VIEW)
        self._view.setOpenLinks(False)
        body.addWidget(self._view, 1)

        self._status = make_label(f"color: {MUTED}; font-size: 12px;")
        body.addWidget(self._status)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setStyleSheet(self.STYLE_INPUT)
        self._input.setPlaceholderText(t("chat_placeholder"))
        self._input.returnPressed.connect(self._send)
        self._send_btn = QPushButton("➤")
        self._send_btn.setFixedSize(36, 34)
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.setStyleSheet(
            "QPushButton { color: #1e1e2e; background: #89b4fa; border: none; border-radius: 8px; font-size: 16px; }"
            "QPushButton:hover { background: #b4befe; }"
            "QPushButton:disabled { background: #45475a; color: #6c7086; }"
        )
        self._send_btn.clicked.connect(self._send)
        row.addWidget(self._input, 1)
        row.addWidget(self._send_btn)
        body.addLayout(row)

    # -----------------------------------------------------------------------
    # Transcript
    # -----------------------------------------------------------------------

    def _add(self, who: str, color: str, text: str) -> None:
        body = html.escape(text).replace("\n", "<br>")
        self._view.append(
            f"<p style='margin: 2px 0 8px 0;'><b style='color:{color};'>{html.escape(who)}</b><br>{body}</p>"
        )

    def _add_note(self, text: str) -> None:
        self._view.append(f"<p style='color:{MUTED}; margin: 0 0 6px 0;'><i>{html.escape(text)}</i></p>")

    def _show_welcome(self) -> None:
        self._view.clear()
        self._add_note(t("chat_welcome"))

    def _clear(self) -> None:
        if self._waiting:
            return
        self._session.clear()
        self._show_welcome()

    # -----------------------------------------------------------------------
    # Exchange
    # -----------------------------------------------------------------------

    def _set_waiting(self, waiting: bool) -> None:
        self._waiting = waiting
        self._input.setEnabled(not waiting)
        self._send_btn.setEnabled(not waiting)
        self._clear_btn.setEnabled(not waiting)
        self._status.setText(t("chat_thinking") if waiting else "")
        if not waiting:
            self._input.setFocus()

    def _send(self) -> None:
        text = self._input.text().strip()
        if not text or self._waiting:
            return
        self._input.clear()
        self._add(t("chat_you"), USER_COLOR, text)
        if self._run_typed_command(text):
            return
        allowed = select_tools(text, t("ai_action_words"), t("ai_search_words"))
        search_first = ""
        if looks_like_order(text, t("ai_force_search_words")):
            allowed.add(SEARCH_TOOL)
            search_first = text.strip()
        prompt = self._build_prompt() + ("" if "*" in allowed else "\n" + t("ai_no_tools"))
        if self._session.send(text, prompt, t("ai_repeat_nudge"), allowed, search_first):
            self._set_waiting(True)

    def _run_typed_command(self, text: str) -> bool:
        """
        'cmd ipconfig', 'ip config /all', 'lance la commande ping google.com':
        run it at once, without asking the model, and show what it printed.

        Returns:
            True if the message was a command request (handled here).
        """
        parsed = safe_commands.parse(text)
        if parsed is None:
            return False
        name, option, target = parsed
        if name is None:
            self._add_note(t("chat_command_refused").format(command=target, allowed=", ".join(safe_commands.COMMANDS)))
            return True
        self._set_waiting(True)
        shown = safe_commands.display(name, target, option)

        def work() -> None:
            self._command_done.emit(shown, safe_commands.run(name, target, option))

        threading.Thread(target=work, daemon=True).start()
        return True

    def _on_command_done(self, shown: str, output: str) -> None:
        self._set_waiting(False)
        self._add_note(f"{t('chat_action').format(action=t('chat_tool_run_command'))}: {shown}")
        body = html.escape(output).replace("\n", "<br>").replace(" ", "&nbsp;")
        self._view.append(f"<p style='margin: 0 0 8px 0; font-family: Consolas, monospace; font-size: 12px;"
                          f" color: #a6e3a1;'>{body}</p>")

    def _on_reply(self, text: str) -> None:
        self._set_waiting(False)
        self._add("Prinny", PRINNY_COLOR, text or t("chat_done"))

    def _on_failed(self, error: str) -> None:
        self._set_waiting(False)
        low = error.lower()
        if "not found" in low:
            message = t("chat_no_model").format(model=self._session.model)
        elif low.startswith("unreachable"):
            message = t("chat_unavailable")
        else:
            message = t("chat_error").format(error=error[:200])
        self._add_note(message)

    def _on_acted(self, name: str, detail: str) -> None:
        text = t("chat_action").format(action=t(f"chat_tool_{name}"))
        self._add_note(f"{text}: {detail}" if detail else text)

    # -----------------------------------------------------------------------
    # Window
    # -----------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._input.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
