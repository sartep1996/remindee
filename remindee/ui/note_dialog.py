from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QTextCharFormat, QTextListFormat,
)
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QFontComboBox, QFrame,
    QHBoxLayout, QLineEdit, QPushButton, QTextEdit,
    QVBoxLayout, QWidget,
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

_FONT_SIZES = [
    "8", "9", "10", "11", "12", "14", "16",
    "18", "20", "24", "28", "32", "36", "48", "64", "72",
]


def _dot_ss(hex_col: str, *, checked: bool) -> str:
    border = "2px solid #1C0800" if checked else "1.5px solid rgba(0,0,0,0.18)"
    return (
        f"QPushButton {{ background: {hex_col}; border: {border}; border-radius: 11px; }}"
        f"QPushButton:hover {{ border: 2px solid rgba(0,0,0,0.45); }}"
    )


class NoteDialog(QDialog):
    """WYSIWYG rich-text note editor."""

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
        self.setMinimumSize(700, 540)
        self.resize(760, 580)
        self.setWindowTitle("Edit Note" if note else "New Note")
        self.setStyleSheet("QDialog { background: white; }")

        self._build()

        if note:
            self._title_edit.setText(note.title or "")
            content = note.body_md or ""
            if content.strip().startswith("<"):
                self._editor.setHtml(content)
            else:
                self._editor.setPlainText(content)
        elif prefill_text:
            self._title_edit.setText(prefill_text)

        self._title_edit.setFocus()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())

        # Content pane (white)
        content = QWidget()
        content.setStyleSheet("background: white;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 16, 24, 8)
        cl.setSpacing(6)

        # Large title input
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Title…")
        self._title_edit.setStyleSheet(
            "QLineEdit {"
            " font-size: 22px; font-weight: 700; font-family: 'Marker Felt', serif;"
            " border: none; border-bottom: 1.5px solid rgba(0,0,0,0.10);"
            " background: transparent; padding: 6px 2px 12px 2px; color: #1C0800;"
            "}"
            "QLineEdit:focus { border-bottom: 2px solid #FF6B35; }"
        )
        cl.addWidget(self._title_edit)

        # Rich-text WYSIWYG body
        self._editor = QTextEdit()
        self._editor.setPlaceholderText(
            "Start writing…\n\n"
            "Use the toolbar above for Bold, Italic, lists, and font changes."
        )
        self._editor.setAcceptRichText(True)
        self._editor.setStyleSheet(
            "QTextEdit {"
            " background: white; border: none;"
            " font-size: 14px; font-family: -apple-system, 'Helvetica Neue', sans-serif;"
            " color: #1C0800; padding: 4px 0;"
            "}"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(0,0,0,0.15); border-radius: 3px; }"
        )
        self._editor.currentCharFormatChanged.connect(self._sync_toolbar)
        cl.addWidget(self._editor, stretch=1)

        root.addWidget(content, stretch=1)
        root.addWidget(self._build_bottom())

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(
            "QWidget { background: #FFF8F2; border-bottom: 1px solid rgba(0,0,0,0.09); }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(2)

        def _sep() -> QFrame:
            f = QFrame()
            f.setFrameShape(QFrame.Shape.VLine)
            f.setFixedWidth(1)
            f.setStyleSheet("background: rgba(0,0,0,0.10); border: none;")
            f.setFixedHeight(22)
            return f

        def _btn(label: str, tip: str, *, checkable: bool = False,
                 bold: bool = False) -> QPushButton:
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.setFixedHeight(30)
            b.setMinimumWidth(28)
            if bold:
                b.setFont(QFont("Helvetica Neue", 13, QFont.Weight.Bold))
            b.setStyleSheet(
                "QPushButton {"
                " background: transparent; border: none; border-radius: 5px;"
                " font-size: 13px; color: #2C0E00; padding: 0 6px;"
                "}"
                "QPushButton:hover   { background: rgba(255,107,53,0.15); }"
                "QPushButton:checked { background: rgba(255,107,53,0.22); color: #D94010; }"
                "QPushButton:pressed { background: rgba(255,107,53,0.30); }"
            )
            return b

        # Undo / Redo
        undo = _btn("↩", "Undo (Cmd+Z)")
        undo.clicked.connect(self._editor.undo)
        redo = _btn("↪", "Redo (Cmd+Shift+Z)")
        redo.clicked.connect(self._editor.redo)
        layout.addWidget(undo)
        layout.addWidget(redo)
        layout.addWidget(_sep())

        # Font family
        self._font_combo = QFontComboBox()
        self._font_combo.setFixedWidth(155)
        self._font_combo.setFixedHeight(30)
        self._font_combo.setStyleSheet(
            "QFontComboBox {"
            " background: white; border: 1px solid rgba(0,0,0,0.14);"
            " border-radius: 5px; padding: 0 6px; font-size: 12px; color: #1C0800;"
            "}"
            "QFontComboBox::drop-down { border: none; width: 16px; }"
            "QFontComboBox QAbstractItemView { background: white; border: 1px solid #ddd; }"
        )
        self._font_combo.currentFontChanged.connect(self._on_font_changed)
        layout.addWidget(self._font_combo)
        layout.addSpacing(4)

        # Font size
        self._size_combo = QComboBox()
        self._size_combo.addItems(_FONT_SIZES)
        self._size_combo.setCurrentText("14")
        self._size_combo.setFixedWidth(58)
        self._size_combo.setFixedHeight(30)
        self._size_combo.setEditable(True)
        self._size_combo.setStyleSheet(
            "QComboBox {"
            " background: white; border: 1px solid rgba(0,0,0,0.14);"
            " border-radius: 5px; padding: 0 4px; font-size: 12px; color: #1C0800;"
            "}"
            "QComboBox::drop-down { border: none; width: 14px; }"
        )
        self._size_combo.currentTextChanged.connect(self._on_size_changed)
        layout.addWidget(self._size_combo)
        layout.addWidget(_sep())

        # Text color
        color_btn = _btn("A", "Text color")
        color_btn.clicked.connect(self._pick_text_color)
        layout.addWidget(color_btn)
        layout.addWidget(_sep())

        # Bold / Italic / Underline
        self._bold_btn      = _btn("B", "Bold",      checkable=True, bold=True)
        self._italic_btn    = _btn("I", "Italic",     checkable=True)
        self._underline_btn = _btn("U", "Underline",  checkable=True)

        self._bold_btn.toggled.connect(self._on_bold)
        self._italic_btn.toggled.connect(self._on_italic)
        self._underline_btn.toggled.connect(self._on_underline)

        layout.addWidget(self._bold_btn)
        layout.addWidget(self._italic_btn)
        layout.addWidget(self._underline_btn)
        layout.addWidget(_sep())

        # Alignment
        for icon, tip, flag in (
            ("⬛︎", "Left",   Qt.AlignmentFlag.AlignLeft),
            ("▬",  "Centre", Qt.AlignmentFlag.AlignHCenter),
            ("⬜︎", "Right",  Qt.AlignmentFlag.AlignRight),
        ):
            b = _btn(icon, f"Align {tip}")
            b.clicked.connect(lambda _, f=flag: self._editor.setAlignment(f))
            layout.addWidget(b)
        layout.addWidget(_sep())

        # Lists
        bullet_btn   = _btn("•—", "Bullet list")
        numbered_btn = _btn("1.", "Numbered list")
        bullet_btn.clicked.connect(self._toggle_bullet)
        numbered_btn.clicked.connect(self._toggle_numbered)
        layout.addWidget(bullet_btn)
        layout.addWidget(numbered_btn)

        layout.addStretch()
        return bar

    def _build_bottom(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(50)
        bar.setStyleSheet(
            "QWidget { background: #FFF8F2; border-top: 1px solid rgba(0,0,0,0.09); }"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        # Note color-label dots
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
            layout.addWidget(dot)

        layout.addStretch()

        convert_btn = QPushButton("→ Reminder")
        convert_btn.setFixedHeight(34)
        convert_btn.setStyleSheet(
            "QPushButton {"
            " background: rgba(255,107,53,0.10); border: 1px solid rgba(255,107,53,0.30);"
            " border-radius: 8px; font-size: 12px; font-weight: 600; color: #FF6B35; padding: 0 14px;"
            "}"
            "QPushButton:hover { background: rgba(255,107,53,0.22); }"
        )
        convert_btn.clicked.connect(self._convert_to_reminder)
        layout.addWidget(convert_btn)

        def _action_btn(label: str) -> QPushButton:
            b = QPushButton(label)
            b.setFixedHeight(34)
            b.setMinimumWidth(80)
            b.setStyleSheet(
                "QPushButton {"
                " background: white; border: 1.5px solid rgba(0,0,0,0.15);"
                " border-radius: 8px; font-size: 13px; font-weight: 500; color: #2C0E00;"
                " padding: 0 16px;"
                "}"
                "QPushButton:hover { border-color: rgba(0,0,0,0.30); }"
            )
            return b

        cancel_btn = _action_btn("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        save_btn = _action_btn("Save")
        save_btn.setDefault(True)
        save_btn.setStyleSheet(
            "QPushButton {"
            " background: #FF6B35; border: none;"
            " border-radius: 8px; font-size: 13px; font-weight: 700; color: white;"
            " padding: 0 20px;"
            "}"
            "QPushButton:hover   { background: #E85A25; }"
            "QPushButton:pressed { background: #D04A18; }"
        )
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        return bar

    # ── Toolbar → editor sync ─────────────────────────────────────────────────

    def _sync_toolbar(self, fmt: QTextCharFormat) -> None:
        """Update toolbar to reflect the format at the current cursor."""
        for widget, value in (
            (self._bold_btn,      fmt.fontWeight() >= QFont.Weight.Bold),
            (self._italic_btn,    fmt.fontItalic()),
            (self._underline_btn, fmt.fontUnderline()),
        ):
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)

        self._font_combo.blockSignals(True)
        self._font_combo.setCurrentFont(fmt.font())
        self._font_combo.blockSignals(False)

        size = fmt.fontPointSize()
        if size > 0:
            self._size_combo.blockSignals(True)
            self._size_combo.setCurrentText(str(int(size)))
            self._size_combo.blockSignals(False)

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _on_font_changed(self, font: QFont) -> None:
        self._editor.setCurrentFont(font)
        self._editor.setFocus()

    def _on_size_changed(self, text: str) -> None:
        try:
            size = float(text)
            if size > 0:
                self._editor.setFontPointSize(size)
                self._editor.setFocus()
        except ValueError:
            pass

    def _on_bold(self, on: bool) -> None:
        self._editor.setFontWeight(QFont.Weight.Bold if on else QFont.Weight.Normal)

    def _on_italic(self, on: bool) -> None:
        self._editor.setFontItalic(on)

    def _on_underline(self, on: bool) -> None:
        self._editor.setFontUnderline(on)

    def _pick_text_color(self) -> None:
        col = QColorDialog.getColor(QColor("#1C0800"), parent=self)
        if col.isValid():
            self._editor.setTextColor(col)
            self._editor.setFocus()

    def _toggle_bullet(self) -> None:
        cursor  = self._editor.textCursor()
        current = cursor.currentList()
        if current and current.format().style() == QTextListFormat.Style.ListDisc:
            cursor.setBlockFormat(cursor.blockFormat())   # remove indent / list
        else:
            fmt = QTextListFormat()
            fmt.setStyle(QTextListFormat.Style.ListDisc)
            cursor.createList(fmt)
        self._editor.setFocus()

    def _toggle_numbered(self) -> None:
        cursor  = self._editor.textCursor()
        current = cursor.currentList()
        if current and current.format().style() == QTextListFormat.Style.ListDecimal:
            cursor.setBlockFormat(cursor.blockFormat())
        else:
            fmt = QTextListFormat()
            fmt.setStyle(QTextListFormat.Style.ListDecimal)
            cursor.createList(fmt)
        self._editor.setFocus()

    # ── Color dots ────────────────────────────────────────────────────────────

    def _pick_color(self, name: str, _hex: str) -> None:
        self._color_label = None if self._color_label == name else name
        for n, dot in self._dot_btns.items():
            h = dict(_COLOR_DOTS)[n]
            dot.setChecked(n == self._color_label)
            dot.setStyleSheet(_dot_ss(h, checked=(n == self._color_label)))

    # ── Save / convert ────────────────────────────────────────────────────────

    def _save(self) -> None:
        title = self._title_edit.text().strip()
        body  = self._editor.toHtml()
        if self._note is None:
            self._note_service.create_note(
                self._user.id,
                title=title,
                body_md=body,
                folder_id=self._folder_id,
                color_label=self._color_label,
            )
        else:
            self._note_service.update_note(
                self._note.id,
                title=title,
                body_md=body,
                color_label=self._color_label,
            )
        self.note_saved.emit()
        self.accept()

    def _convert_to_reminder(self) -> None:
        from remindee.ui.reminder_dialog import ReminderDialog
        scheduler = getattr(self.parent(), "_scheduler", None)
        if scheduler is None:
            return
        dlg = ReminderDialog(
            self._user, scheduler,
            prefill_name=self._title_edit.text().strip() or "Untitled",
            parent=self,
        )
        if dlg.exec():
            self.accept()
