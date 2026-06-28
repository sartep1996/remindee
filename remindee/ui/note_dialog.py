from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from remindee.models.note import Note
from remindee.models.user import User
from remindee.services.note_service import NoteService

_COLOR_DOTS: list[tuple[str, str]] = [
    ("orange", "#FF6B35"),
    ("red",    "#EF4444"),
    ("green",  "#22C55E"),
    ("blue",   "#3B82F6"),
    ("purple", "#A855F7"),
]


def _dot_ss(hex_col: str, *, checked: bool) -> str:
    border = "2px solid #1C0800" if checked else "1.5px solid rgba(0,0,0,0.18)"
    return (
        f"QPushButton {{ background: {hex_col}; border: {border}; border-radius: 11px; }}"
        f"QPushButton:hover {{ border: 2px solid rgba(0,0,0,0.45); }}"
    )


class NoteDialog(QDialog):
    """Create / edit a note. Opens as a modal dialog."""

    note_saved = Signal()

    def __init__(
        self,
        user: User,
        note_service: NoteService,
        note: Note | None = None,
        folder_id: int | None = None,
        prefill_text: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._user         = user
        self._note_service = note_service
        self._note         = note
        self._folder_id    = folder_id
        self._color_label: str | None = note.color_label if note else None

        self.setModal(True)
        self.setMinimumSize(540, 500)
        self.setWindowTitle("Edit Note" if note else "New Note")

        self._build()

        if note:
            self._title_edit.setText(note.title or "")
            self._body_edit.setPlainText(note.body_md or "")
        elif prefill_text:
            self._title_edit.setText(prefill_text)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        # Title
        self._title_edit = QLineEdit()
        self._title_edit.setObjectName("NoteDialogTitle")
        self._title_edit.setPlaceholderText("Note title…")
        self._title_edit.setStyleSheet(
            "QLineEdit#NoteDialogTitle {"
            " font-size: 18px; font-weight: 700;"
            " border: none; border-bottom: 1.5px solid rgba(255,107,53,0.30);"
            " border-radius: 0; background: transparent;"
            " padding: 8px 4px 8px 4px; color: @text;"
            "}"
            "QLineEdit#NoteDialogTitle:focus { border-bottom-color: #FF6B35; }"
        )
        root.addWidget(self._title_edit)

        # Markdown toolbar
        toolbar = self._build_toolbar()
        root.addWidget(toolbar)

        # Body editor
        self._body_edit = QPlainTextEdit()
        self._body_edit.setObjectName("NoteDialogBody")
        self._body_edit.setPlaceholderText("Write in Markdown…  **bold**  *italic*  # heading")
        self._body_edit.setStyleSheet(
            "QPlainTextEdit#NoteDialogBody {"
            " background: rgba(255,255,255,0.85);"
            " border: 1.5px solid rgba(255,107,53,0.15);"
            " border-radius: 10px;"
            " font-size: 14px; font-family: 'Menlo', 'Monaco', 'Courier New', monospace;"
            " color: #1C0800; padding: 12px;"
            "}"
            "QPlainTextEdit#NoteDialogBody:focus {"
            " border-color: rgba(255,107,53,0.40);"
            "}"
        )
        root.addWidget(self._body_edit, stretch=1)

        # Bottom bar
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self._dot_btns: dict[str, QPushButton] = {}
        for name, hex_col in _COLOR_DOTS:
            dot = QPushButton()
            dot.setFixedSize(22, 22)
            dot.setCheckable(True)
            dot.setChecked(self._color_label == name)
            dot.setToolTip(name.capitalize())
            dot.setStyleSheet(_dot_ss(hex_col, checked=(self._color_label == name)))
            dot.clicked.connect(lambda _, n=name, h=hex_col: self._pick_color(n, h))
            self._dot_btns[name] = dot
            bottom.addWidget(dot)

        bottom.addStretch()

        # "→ Reminder" conversion button
        convert_btn = QPushButton("→ Reminder")
        convert_btn.setObjectName("NoteConvertBtn")
        convert_btn.setFixedHeight(34)
        convert_btn.setStyleSheet(
            "QPushButton#NoteConvertBtn {"
            " background: rgba(255,107,53,0.10); border: 1px solid rgba(255,107,53,0.30);"
            " border-radius: 8px; font-size: 12px; font-weight: 600; color: #FF6B35; padding: 0 14px;"
            "}"
            "QPushButton#NoteConvertBtn:hover { background: rgba(255,107,53,0.20); }"
        )
        convert_btn.clicked.connect(self._convert_to_reminder)
        bottom.addWidget(convert_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setMinimumHeight(34)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setMinimumHeight(34)
        save_btn.setMinimumWidth(80)
        save_btn.clicked.connect(self._save)
        bottom.addWidget(save_btn)

        root.addLayout(bottom)

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setObjectName("NoteToolbar")
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet(
            "QWidget#NoteToolbar {"
            " background: rgba(255,107,53,0.06);"
            " border: 1px solid rgba(255,107,53,0.12);"
            " border-radius: 8px;"
            "}"
        )
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(6, 0, 6, 0)
        tb.setSpacing(2)

        def _btn(label: str, tip: str) -> QPushButton:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setFixedSize(30, 28)
            b.setStyleSheet(
                "QPushButton { background: transparent; border: none; border-radius: 5px;"
                " font-size: 13px; font-weight: 600; color: #1C0800; }"
                "QPushButton:hover { background: rgba(255,107,53,0.18); }"
            )
            return b

        bold_btn = _btn("B", "Bold (wrap in **)")
        bold_btn.clicked.connect(lambda: self._wrap("**", "**"))

        italic_btn = _btn("I", "Italic (wrap in *)")
        italic_btn.clicked.connect(lambda: self._wrap("*", "*"))

        code_btn = _btn("`", "Inline code")
        code_btn.clicked.connect(lambda: self._wrap("`", "`"))

        h1_btn = _btn("H1", "Heading 1")
        h1_btn.clicked.connect(lambda: self._prefix("# "))

        h2_btn = _btn("H2", "Heading 2")
        h2_btn.clicked.connect(lambda: self._prefix("## "))

        list_btn = _btn("•", "Bullet list")
        list_btn.clicked.connect(lambda: self._prefix("- "))

        hint = QLabel("Markdown")
        hint.setStyleSheet("color: rgba(140,80,48,0.5); font-size: 11px; padding: 0 4px;")

        for w in (bold_btn, italic_btn, code_btn, h1_btn, h2_btn, list_btn):
            tb.addWidget(w)
        tb.addStretch()
        tb.addWidget(hint)

        return toolbar

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _wrap(self, before: str, after: str) -> None:
        cur = self._body_edit.textCursor()
        if cur.hasSelection():
            cur.insertText(before + cur.selectedText() + after)
        else:
            cur.insertText(before + after)
            pos = cur.position() - len(after)
            cur.setPosition(pos)
            self._body_edit.setTextCursor(cur)
        self._body_edit.setFocus()

    def _prefix(self, prefix: str) -> None:
        cur = self._body_edit.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.StartOfLine)
        cur.select(QTextCursor.SelectionType.LineUnderCursor)
        if not cur.selectedText().startswith(prefix):
            cur.movePosition(QTextCursor.MoveOperation.StartOfLine)
            cur.insertText(prefix)
        self._body_edit.setFocus()

    # ── Color picker ─────────────────────────────────────────────────────────

    def _pick_color(self, name: str, hex_col: str) -> None:
        self._color_label = None if self._color_label == name else name
        for n, dot in self._dot_btns.items():
            h = dict(_COLOR_DOTS)[n]
            dot.setChecked(n == self._color_label)
            dot.setStyleSheet(_dot_ss(h, checked=(n == self._color_label)))

    # ── Save / convert ────────────────────────────────────────────────────────

    def _save(self) -> None:
        title   = self._title_edit.text().strip()
        body_md = self._body_edit.toPlainText()
        if self._note is None:
            self._note_service.create_note(
                self._user.id,
                title=title,
                body_md=body_md,
                folder_id=self._folder_id,
                color_label=self._color_label,
            )
        else:
            self._note_service.update_note(
                self._note.id,
                title=title,
                body_md=body_md,
                color_label=self._color_label,
            )
        self.note_saved.emit()
        self.accept()

    def _convert_to_reminder(self) -> None:
        """Save note content as a Reminder via ReminderDialog, then close."""
        kwargs = self._note_service.note_to_reminder_kwargs(
            self._note
        ) if self._note else {
            "prefill_name":    self._title_edit.text().strip() or "Untitled",
            "prefill_details": self._body_edit.toPlainText(),
        }
        from remindee.ui.reminder_dialog import ReminderDialog
        parent_win = self.parent()
        scheduler  = getattr(parent_win, "_scheduler", None)
        if scheduler is None:
            return
        dlg = ReminderDialog(
            self._user, scheduler,
            prefill_name=kwargs.get("prefill_name", ""),
            parent=self,
        )
        if dlg.exec():
            self.accept()
