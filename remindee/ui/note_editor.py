from __future__ import annotations

import markdown

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

# Injected into preview HTML so it renders with legible colors
PREVIEW_CSS = """
<style>
body { font-family: -apple-system, sans-serif; font-size: 14px;
       color: #1C0800; background: transparent; margin: 12px; }
h1, h2 { font-weight: 700; }
code { background: rgba(0,0,0,0.07); padding: 2px 5px; border-radius: 4px; }
pre code { display: block; padding: 10px; }
</style>
"""

_COLOR_DOTS: list[tuple[str, str]] = [
    ("orange", "#FF6B35"),
    ("red",    "#EF4444"),
    ("green",  "#22C55E"),
    ("blue",   "#3B82F6"),
    ("purple", "#A855F7"),
    ("none",   "#CCCCCC"),
]

_DOT_SELECTED_BORDER = "#1C0800"
_DOT_SIZE = 20


class NoteEditor(QWidget):
    """Split-pane markdown editor for a single note."""

    note_saved        = Signal(int, str, str)   # (note_id, title, body_md)
    convert_to_reminder = Signal(int)            # note_id
    delete_requested  = Signal(int)              # note_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NoteEditor")

        self._note_id:    int | None = None
        self._color_label: str | None = None
        self._preview_visible = True
        self._block_autosave  = False

        # Debounce timers
        self._save_timer    = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(self._emit_save)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(400)
        self._preview_timer.timeout.connect(self._update_preview)

        self._build()
        self.clear()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Title input ───────────────────────────────────────────────────────
        self._title_edit = QLineEdit()
        self._title_edit.setObjectName("NoteTitle")
        self._title_edit.setPlaceholderText("Note title…")
        self._title_edit.setStyleSheet(
            "QLineEdit#NoteTitle {"
            " font-size: 18px; font-weight: 700;"
            " border: none; border-bottom: 1.5px solid rgba(255,107,53,0.22);"
            " border-radius: 0; background: transparent;"
            " padding: 14px 16px 10px 16px;"
            " color: inherit;"
            "}"
            "QLineEdit#NoteTitle:focus {"
            " border-bottom-color: #FF6B35; background: transparent;"
            "}"
        )
        self._title_edit.textChanged.connect(self._on_content_changed)
        root.addWidget(self._title_edit)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setObjectName("NoteToolbar")
        toolbar.setFixedHeight(38)
        toolbar.setStyleSheet(
            "QWidget#NoteToolbar {"
            " background: rgba(255,107,53,0.06);"
            " border-bottom: 1px solid rgba(255,107,53,0.15);"
            "}"
        )
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 0, 8, 0)
        tb_layout.setSpacing(2)

        def _tb_btn(label: str, tip: str) -> QPushButton:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.setFixedSize(30, 28)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; border-radius: 5px;"
                " font-size: 13px; font-weight: 600; color: #1C0800; }"
                "QPushButton:hover { background: rgba(255,107,53,0.18); }"
                "QPushButton:pressed { background: rgba(255,107,53,0.30); }"
            )
            return btn

        bold_btn = _tb_btn("B", "Bold")
        bold_btn.setFont(QFont("Helvetica Neue", 13, QFont.Weight.Bold))
        bold_btn.clicked.connect(lambda: self._wrap_selection("**", "**"))

        italic_btn = _tb_btn("I", "Italic")
        italic_btn.setFont(QFont("Helvetica Neue", 13, QFont.Weight.Normal))
        italic_btn.clicked.connect(lambda: self._wrap_selection("*", "*"))

        code_btn = _tb_btn("`", "Inline code")
        code_btn.clicked.connect(lambda: self._wrap_selection("`", "`"))

        h1_btn = _tb_btn("H1", "Heading 1")
        h1_btn.clicked.connect(lambda: self._prefix_line("# "))

        h2_btn = _tb_btn("H2", "Heading 2")
        h2_btn.clicked.connect(lambda: self._prefix_line("## "))

        list_btn = _tb_btn("•", "Bullet list")
        list_btn.clicked.connect(lambda: self._prefix_line("- "))

        rule_btn = _tb_btn("─", "Horizontal rule")
        rule_btn.clicked.connect(self._insert_rule)

        for btn in (bold_btn, italic_btn, code_btn, h1_btn, h2_btn, list_btn, rule_btn):
            tb_layout.addWidget(btn)

        tb_layout.addStretch()

        self._preview_btn = QPushButton("Preview ▕")
        self._preview_btn.setObjectName("NotePreviewToggle")
        self._preview_btn.setCheckable(True)
        self._preview_btn.setChecked(True)
        self._preview_btn.setFixedHeight(26)
        self._preview_btn.setStyleSheet(
            "QPushButton#NotePreviewToggle {"
            " background: rgba(255,107,53,0.12); border: 1px solid rgba(255,107,53,0.25);"
            " border-radius: 5px; font-size: 12px; font-weight: 600; color: #FF6B35;"
            " padding: 0 10px;"
            "}"
            "QPushButton#NotePreviewToggle:checked {"
            " background: #FF6B35; color: #ffffff;"
            "}"
            "QPushButton#NotePreviewToggle:hover { border-color: #FF6B35; }"
        )
        self._preview_btn.toggled.connect(self._toggle_preview)
        tb_layout.addWidget(self._preview_btn)

        root.addWidget(toolbar)

        # ── Editor / Preview splitter ─────────────────────────────────────────
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("NoteEditorSplitter")
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet(
            "QSplitter#NoteEditorSplitter::handle { background: rgba(255,107,53,0.15); }"
        )

        self._editor = QPlainTextEdit()
        self._editor.setObjectName("NoteBodyEditor")
        self._editor.setPlaceholderText("Write your note in Markdown…")
        self._editor.setStyleSheet(
            "QPlainTextEdit#NoteBodyEditor {"
            " background: transparent; border: none;"
            " font-size: 14px; font-family: 'Courier New', monospace;"
            " padding: 12px 14px; color: inherit;"
            "}"
        )
        self._editor.textChanged.connect(self._on_content_changed)
        self._splitter.addWidget(self._editor)

        self._preview = QTextBrowser()
        self._preview.setObjectName("NotePreviewPane")
        self._preview.setOpenExternalLinks(True)
        self._preview.setStyleSheet(
            "QTextBrowser#NotePreviewPane {"
            " background: rgba(255,252,248,0.60); border: none;"
            " border-left: 1px solid rgba(255,107,53,0.15);"
            " font-size: 14px; padding: 4px;"
            "}"
        )
        self._splitter.addWidget(self._preview)
        self._splitter.setSizes([1, 1])

        root.addWidget(self._splitter, stretch=1)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom = QWidget()
        bottom.setObjectName("NoteBottomBar")
        bottom.setFixedHeight(46)
        bottom.setStyleSheet(
            "QWidget#NoteBottomBar {"
            " background: rgba(255,107,53,0.04);"
            " border-top: 1px solid rgba(255,107,53,0.15);"
            "}"
        )
        bot_layout = QHBoxLayout(bottom)
        bot_layout.setContentsMargins(12, 0, 12, 0)
        bot_layout.setSpacing(6)

        # Color dot buttons
        self._dot_buttons: dict[str, QPushButton] = {}
        for color_name, hex_color in _COLOR_DOTS:
            dot = QPushButton()
            dot.setFixedSize(_DOT_SIZE, _DOT_SIZE)
            dot.setCheckable(True)
            dot.setToolTip(color_name.capitalize())
            dot.setStyleSheet(_dot_style(hex_color, checked=False))
            dot.clicked.connect(lambda checked, cn=color_name, hx=hex_color: self._set_color(cn, hx))
            self._dot_buttons[color_name] = dot
            bot_layout.addWidget(dot)

        bot_layout.addStretch()

        convert_btn = QPushButton("→ Reminder")
        convert_btn.setObjectName("NoteConvertBtn")
        convert_btn.setFixedHeight(30)
        convert_btn.setStyleSheet(
            "QPushButton#NoteConvertBtn {"
            " background: rgba(255,107,53,0.12); border: 1px solid rgba(255,107,53,0.30);"
            " border-radius: 7px; font-size: 12px; font-weight: 600; color: #FF6B35;"
            " padding: 0 12px;"
            "}"
            "QPushButton#NoteConvertBtn:hover { background: rgba(255,107,53,0.22); }"
        )
        convert_btn.clicked.connect(self._on_convert)
        bot_layout.addWidget(convert_btn)

        del_btn = QPushButton("🗑")
        del_btn.setObjectName("NoteDeleteBtn")
        del_btn.setFixedSize(30, 30)
        del_btn.setToolTip("Delete note")
        del_btn.setStyleSheet(
            "QPushButton#NoteDeleteBtn {"
            " background: transparent; border: 1px solid rgba(239,68,68,0.25);"
            " border-radius: 7px; font-size: 15px; color: #EF4444;"
            "}"
            "QPushButton#NoteDeleteBtn:hover { background: rgba(239,68,68,0.12); }"
        )
        del_btn.clicked.connect(self._on_delete)
        bot_layout.addWidget(del_btn)

        root.addWidget(bottom)

        # ── Empty-state overlay ───────────────────────────────────────────────
        self._empty_lbl = QLabel("Select a note or create a new one")
        self._empty_lbl.setObjectName("NoteEmptyState")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            "color: rgba(140,80,48,0.55); font-size: 15px; font-weight: 500;"
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def load_note(
        self,
        note_id: int,
        title: str,
        body_md: str,
        color_label: str | None = None,
    ) -> None:
        self._block_autosave = True
        self._note_id     = note_id
        self._color_label = color_label

        self._title_edit.setText(title or "")
        self._editor.setPlainText(body_md or "")

        # Update color dots
        for cn, dot in self._dot_buttons.items():
            hex_color = dict(_COLOR_DOTS)[cn]
            dot.setChecked(cn == (color_label or "none"))
            dot.setStyleSheet(_dot_style(hex_color, checked=(cn == (color_label or "none"))))

        self._show_editor(True)
        self._update_preview()
        self._block_autosave = False

    def clear(self) -> None:
        """Show the empty state — no note loaded."""
        self._block_autosave = True
        self._note_id = None
        self._title_edit.clear()
        self._editor.clear()
        self._preview.clear()
        self._show_editor(False)
        self._block_autosave = False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _show_editor(self, visible: bool) -> None:
        self._title_edit.setVisible(visible)
        self._splitter.setVisible(visible)

    def _on_content_changed(self) -> None:
        if self._block_autosave or self._note_id is None:
            return
        self._save_timer.start()
        self._preview_timer.start()

    def _emit_save(self) -> None:
        if self._note_id is None:
            return
        title   = self._title_edit.text().strip()
        body_md = self._editor.toPlainText()
        self.note_saved.emit(self._note_id, title, body_md)

    def _update_preview(self) -> None:
        body = self._editor.toPlainText()
        html = markdown.markdown(body, extensions=["nl2br"])
        self._preview.setHtml(PREVIEW_CSS + html)

    def _toggle_preview(self, show: bool) -> None:
        self._preview_visible = show
        self._preview.setVisible(show)
        if show:
            self._update_preview()

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _wrap_selection(self, before: str, after: str) -> None:
        cur = self._editor.textCursor()
        if cur.hasSelection():
            text = before + cur.selectedText() + after
        else:
            text = before + after
        cur.insertText(text)
        # Move cursor to between the markers if no selection
        if not cur.hasSelection():
            pos = cur.position() - len(after)
            cur.setPosition(pos)
            self._editor.setTextCursor(cur)
        self._editor.setFocus()

    def _prefix_line(self, prefix: str) -> None:
        cur = self._editor.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.StartOfLine)
        # Check if prefix already there
        cur.select(QTextCursor.SelectionType.LineUnderCursor)
        line = cur.selectedText()
        cur.movePosition(QTextCursor.MoveOperation.StartOfLine)
        if not line.startswith(prefix):
            cur.insertText(prefix)
        self._editor.setFocus()

    def _insert_rule(self) -> None:
        cur = self._editor.textCursor()
        cur.insertText("\n---\n")
        self._editor.setFocus()

    # ── Color dots ────────────────────────────────────────────────────────────

    def _set_color(self, color_name: str, hex_color: str) -> None:
        # Toggle — clicking the active color deselects it
        if self._color_label == color_name or (color_name == "none" and self._color_label is None):
            new_label = None
        else:
            new_label = None if color_name == "none" else color_name

        self._color_label = new_label

        for cn, dot in self._dot_buttons.items():
            hx = dict(_COLOR_DOTS)[cn]
            active = (cn == (new_label or "none")) if new_label is not None else (cn == "none")
            dot.setChecked(active)
            dot.setStyleSheet(_dot_style(hx, checked=active))

        if self._note_id is not None:
            self.note_saved.emit(
                self._note_id,
                self._title_edit.text().strip(),
                self._editor.toPlainText(),
            )

    # ── Bottom-bar buttons ────────────────────────────────────────────────────

    def _on_convert(self) -> None:
        if self._note_id is not None:
            self.convert_to_reminder.emit(self._note_id)

    def _on_delete(self) -> None:
        if self._note_id is not None:
            self.delete_requested.emit(self._note_id)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dot_style(hex_color: str, *, checked: bool) -> str:
    border = f"2px solid {_DOT_SELECTED_BORDER}" if checked else "1.5px solid rgba(0,0,0,0.18)"
    return (
        f"QPushButton {{"
        f" background: {hex_color};"
        f" border: {border};"
        f" border-radius: {_DOT_SIZE // 2}px;"
        f"}}"
        f"QPushButton:hover {{ border: 2px solid rgba(0,0,0,0.45); }}"
    )
