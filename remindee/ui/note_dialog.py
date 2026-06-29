from __future__ import annotations

import base64
import json
import mimetypes
import os
import random
import tempfile

from PySide6.QtCore import QBuffer, QByteArray, QEvent, QIODevice, Qt, QRectF, QSize, QUrl, Signal
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QIcon, QImage, QPainter, QPen, QPixmap,
    QStandardItem, QStandardItemModel,
    QTextCharFormat, QTextFrameFormat, QTextListFormat, QTextTableFormat,
)
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from remindee.models.note import Note
from remindee.models.user import User
from remindee.services.note_service import NoteService
from remindee.ui.reminder_card import (
    _DARK_BASES, _SCHEMES, _STYLES, _draw_base,
)

_COLOR_DOTS: list[tuple[str, str]] = [
    ("orange", "#FF6B35"),
    ("red",    "#EF4444"),
    ("green",  "#22C55E"),
    ("blue",   "#3B82F6"),
    ("purple", "#A855F7"),
]

_FONT_GROUPS = [
    ("Handwritten", ["Marker Felt", "Bradley Hand", "Chalkboard SE", "Zapfino"]),
    ("Traditional", ["Times New Roman", "Baskerville", "Georgia", "Palatino"]),
    ("Modern",      ["Helvetica Neue", "Arial", "Futura", "Verdana"]),
    ("Monospace",   ["Courier New", "Menlo", "Monaco"]),
]

_FONT_OPTIONS = [f for _, fonts in _FONT_GROUPS for f in fonts]

_FONT_SIZES = [
    "8", "9", "10", "11", "12", "14", "16",
    "18", "20", "24", "28", "32", "36", "48",
]

_TITLE_FONT_SIZE = 16

# Word-style quick text-color palette
_TEXT_COLORS: list[tuple[str, str]] = [
    ("Black",      "#000000"),
    ("Dark Red",   "#C00000"),
    ("Red",        "#FF0000"),
    ("Orange",     "#FF6B35"),
    ("Gold",       "#FFD700"),
    ("Dark Green", "#00A550"),
    ("Teal",       "#008080"),
    ("Blue",       "#0070C0"),
    ("Dark Blue",  "#003087"),
    ("Purple",     "#7030A0"),
    ("Dark Gray",  "#404040"),
    ("Gray",       "#808080"),
]


# ── Table insert dialog ───────────────────────────────────────────────────────

class _TableDialog(QDialog):
    """Minimal row/column picker for inserting a table."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Table")
        self.setModal(True)
        self.setFixedSize(230, 130)
        layout = QFormLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)

        self._rows = QSpinBox()
        self._rows.setRange(1, 20)
        self._rows.setValue(3)
        self._cols = QSpinBox()
        self._cols.setRange(1, 20)
        self._cols.setValue(3)
        layout.addRow("Rows:", self._rows)
        layout.addRow("Columns:", self._cols)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def values(self) -> tuple[int, int]:
        return self._rows.value(), self._cols.value()


# ── Icon helpers ──────────────────────────────────────────────────────────────

def _para_align_icon(align: str, color: QColor, size: int = 18) -> QIcon:
    """Word-style paragraph alignment icon drawn with QPainter."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    w = float(size)
    if align == "left":
        segs = [(0.0, 0.95), (0.0, 0.60), (0.0, 0.82), (0.0, 0.50)]
    elif align == "center":
        segs = [(0.05, 0.95), (0.20, 0.80), (0.10, 0.90), (0.25, 0.75)]
    else:
        segs = [(0.05, 1.0), (0.40, 1.0), (0.18, 1.0), (0.50, 1.0)]
    for i, (x1, x2) in enumerate(segs):
        y = 2 + i * 4
        p.drawLine(int(x1 * w), y, int(x2 * w), y)
    p.end()
    return QIcon(pix)


def _list_icon(numbered: bool, color: QColor, size: int = 18) -> QIcon:
    """Bullet or numbered list icon drawn with QPainter."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(color, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    w = float(size)
    for row_idx, y in enumerate((3, 8, 13)):
        if numbered:
            p.setFont(QFont("Helvetica Neue", 7, QFont.Weight.Bold))
            p.drawText(0, y - 1, 6, 7, Qt.AlignmentFlag.AlignCenter, str(row_idx + 1))
        else:
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(1, y, 4, 4)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color, 1.4))
        p.drawLine(8, y + 2, int(0.95 * w), y + 2)
    p.end()
    return QIcon(pix)


def _dot_ss(hex_col: str, *, checked: bool) -> str:
    """Word-style square color swatch — thick dark border + checkmark when selected."""
    if checked:
        return (
            f"QPushButton {{ background: {hex_col}; border: 2.5px solid rgba(0,0,0,0.75);"
            f" border-radius: 3px; color: white; font-size: 11px; font-weight: 700; }}"
            f"QPushButton:hover {{ border: 2.5px solid rgba(0,0,0,0.90); }}"
        )
    return (
        f"QPushButton {{ background: {hex_col}; border: 1px solid rgba(0,0,0,0.22);"
        f" border-radius: 3px; color: transparent; font-size: 11px; }}"
        f"QPushButton:hover {{ border: 2px solid rgba(0,0,0,0.55); }}"
    )


class NoteDialog(QDialog):
    """WYSIWYG rich-text note editor — painted art background matching ReminderDialog."""

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
        self._last_text_focus: str = "title"

        # Load any existing file attachments stored as JSON
        att_json = getattr(note, "attachments", None) if note else None
        self._attachments: list[dict] = json.loads(att_json) if att_json else []

        # Art seed — mirrors NoteCard seed logic so dialog art matches the card
        if note and note.id:
            seed = note.id & 0x7FFFFFFF
        else:
            uid  = getattr(user, "id", None) or 0
            seed = (uid * 1_337 + 42) & 0x7FFFFFFF or 5
        self._art_seed    = seed
        self._art_palette = _SCHEMES[seed % len(_SCHEMES)]
        self._art_dark    = (seed * 11 + 5) % 5 == 0
        self._art_style   = (seed * 17 + 5) % len(_STYLES)

        self.setAutoFillBackground(False)
        self.setObjectName("NoteDialog")
        self.setWindowTitle("Edit Note" if note else "New Note")
        self.setMinimumSize(700, 560)
        self.resize(760, 620)
        self.setModal(True)

        self._build()
        self._refresh_att_panel()

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

    # ── Custom background ─────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r   = QRectF(self.rect())
        rng = random.Random(self._art_seed)

        if self._art_dark:
            base = _DARK_BASES[self._art_seed % len(_DARK_BASES)]
            p.fillRect(r, QColor(base.red(), base.green(), base.blue(), 255))
        else:
            p.fillRect(r, QColor(255, 252, 248, 255))
            _draw_base(p, r, rng, self._art_palette, self._art_seed)

        _STYLES[self._art_style](p, r, rng, self._art_palette)

        if self._art_dark:
            p.fillRect(r, QColor(0, 0, 0, 148))
        else:
            p.fillRect(r, QColor(255, 255, 255, 155))

    # ── Color helpers ─────────────────────────────────────────────────────────

    def _text_col(self) -> str:
        return "rgba(238,222,205,0.97)" if self._art_dark else "#1C0800"

    def _q_text_col(self) -> QColor:
        return QColor(238, 222, 205) if self._art_dark else QColor(28, 8, 0)

    def _input_ss(self) -> str:
        if self._art_dark:
            return (
                "background: rgba(255,255,255,0.10); border: 1.5px solid rgba(255,255,255,0.18);"
                " border-radius: 10px; color: rgba(238,222,205,0.97); font-size: 14px;"
                " padding: 11px 14px;"
            )
        return (
            "background: rgba(255,255,255,0.82); border: 1.5px solid rgba(255,107,53,0.22);"
            " border-radius: 10px; color: #1C0800; font-size: 14px;"
            " padding: 11px 14px;"
        )

    def _combo_ss(self) -> str:
        # padding-right: 4px — the ::drop-down width already reserves the arrow zone
        if self._art_dark:
            return (
                "QComboBox { background: rgba(255,255,255,0.10);"
                " border: 1.5px solid rgba(255,255,255,0.18);"
                " border-radius: 7px; color: rgba(238,222,205,0.97);"
                " font-size: 12px; padding: 3px 4px 3px 8px; }"
                "QComboBox::drop-down { width: 20px; border: none; }"
                "QComboBox QAbstractItemView {"
                " background: rgba(28,18,42,0.97); color: rgba(238,222,205,0.97);"
                " selection-background-color: rgba(255,255,255,0.20); }"
            )
        return (
            "QComboBox { background: rgba(255,255,255,0.82);"
            " border: 1.5px solid rgba(255,107,53,0.22);"
            " border-radius: 7px; color: #1C0800; font-size: 12px;"
            " padding: 3px 4px 3px 8px; }"
            "QComboBox::drop-down { width: 20px; border: none; }"
            "QComboBox QAbstractItemView {"
            " background: rgba(255,252,248,0.97); color: #1C0800;"
            " selection-background-color: #FF6B35; selection-color: white; }"
        )

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_content(), stretch=1)
        root.addWidget(self._build_bottom())

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(46)
        if self._art_dark:
            bar.setStyleSheet(
                "background: rgba(0,0,0,0.25);"
                " border-bottom: 1px solid rgba(255,255,255,0.10);"
            )
        else:
            bar.setStyleSheet(
                "background: rgba(255,255,255,0.30);"
                " border-bottom: 1px solid rgba(0,0,0,0.08);"
            )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(2)

        tc      = self._text_col()
        qt_col  = self._q_text_col()

        def _sep() -> QFrame:
            f = QFrame()
            f.setFrameShape(QFrame.Shape.VLine)
            f.setFixedWidth(1)
            f.setFixedHeight(22)
            col = "rgba(255,255,255,0.20)" if self._art_dark else "rgba(0,0,0,0.12)"
            f.setStyleSheet(f"background: {col}; border: none;")
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
            hover = "rgba(255,255,255,0.20)" if self._art_dark else "rgba(255,107,53,0.15)"
            chk   = "rgba(255,255,255,0.30)" if self._art_dark else "rgba(255,107,53,0.22)"
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; border-radius: 5px;"
                f" font-size: 13px; color: {tc}; padding: 0 6px; }}"
                f"QPushButton:hover   {{ background: {hover}; }}"
                f"QPushButton:checked {{ background: {chk}; }}"
                f"QPushButton:pressed {{ background: {hover}; }}"
            )
            return b

        def _icon_btn(icon: QIcon, tip: str, *, checkable: bool = False) -> QPushButton:
            b = QPushButton()
            b.setIcon(icon)
            b.setIconSize(QSize(18, 18))
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.setFixedSize(30, 30)
            hover = "rgba(255,255,255,0.20)" if self._art_dark else "rgba(255,107,53,0.15)"
            chk   = "rgba(255,255,255,0.30)" if self._art_dark else "rgba(255,107,53,0.22)"
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; border-radius: 5px; }}"
                f"QPushButton:hover   {{ background: {hover}; }}"
                f"QPushButton:checked {{ background: {chk}; }}"
            )
            return b

        # Undo / Redo
        undo = _btn("↩", "Undo (Cmd+Z)")
        undo.clicked.connect(lambda: self._editor.undo())
        redo = _btn("↪", "Redo (Cmd+Shift+Z)")
        redo.clicked.connect(lambda: self._editor.redo())
        layout.addWidget(undo)
        layout.addWidget(redo)
        layout.addWidget(_sep())

        # Font family — grouped QComboBox avoids macOS QFontComboBox popup issues
        self._font_combo = QComboBox()
        self._font_combo.setFixedWidth(152)
        self._font_combo.setFixedHeight(30)
        self._font_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        font_model = QStandardItemModel()
        for group_name, fonts in _FONT_GROUPS:
            hdr = QStandardItem(f"  {group_name}")
            hdr.setEnabled(False)
            hdr.setFont(QFont("Helvetica Neue", 10))
            font_model.appendRow(hdr)
            for fname in fonts:
                item = QStandardItem(f"  {fname}")
                item.setFont(QFont(fname, 12))
                item.setData(fname, Qt.ItemDataRole.UserRole)
                font_model.appendRow(item)
        self._font_combo.setModel(font_model)
        self._font_combo.setCurrentIndex(1)
        self._font_combo.setStyleSheet(self._combo_ss())
        self._font_combo.currentIndexChanged.connect(self._on_font_index_changed)
        layout.addWidget(self._font_combo)
        layout.addSpacing(3)

        # Font size
        self._size_combo = QComboBox()
        self._size_combo.addItems(_FONT_SIZES)
        self._size_combo.setCurrentText("14")
        self._size_combo.setFixedWidth(66)
        self._size_combo.setFixedHeight(30)
        self._size_combo.setEditable(True)
        self._size_combo.setStyleSheet(self._combo_ss())
        self._size_combo.currentTextChanged.connect(self._on_size_changed)
        layout.addWidget(self._size_combo)
        layout.addWidget(_sep())

        # Text color — Word-style button with quick-color menu
        color_btn = _btn("A", "Text color")
        color_menu = QMenu(color_btn)
        for col_name, hex_col in _TEXT_COLORS:
            pix = QPixmap(14, 14)
            pix.fill(QColor(hex_col))
            action = color_menu.addAction(QIcon(pix), col_name)
            action.triggered.connect(
                lambda _=False, c=hex_col: (
                    self._editor.setTextColor(QColor(c)),
                    self._editor.setFocus(),
                )
            )
        color_menu.addSeparator()
        more_action = color_menu.addAction("More colors…")
        more_action.triggered.connect(self._pick_text_color)
        color_btn.setMenu(color_menu)
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

        # Alignment — Word-style paragraph icons drawn with QPainter
        for align, tip, flag in (
            ("left",   "Align Left",   Qt.AlignmentFlag.AlignLeft),
            ("center", "Align Centre", Qt.AlignmentFlag.AlignHCenter),
            ("right",  "Align Right",  Qt.AlignmentFlag.AlignRight),
        ):
            b = _icon_btn(_para_align_icon(align, qt_col), tip)
            b.clicked.connect(lambda _, f=flag: self._editor.setAlignment(f))
            layout.addWidget(b)
        layout.addWidget(_sep())

        # Lists — QPainter-drawn icons
        bullet_btn   = _icon_btn(_list_icon(False, qt_col), "Bullet list")
        numbered_btn = _icon_btn(_list_icon(True,  qt_col), "Numbered list")
        bullet_btn.clicked.connect(self._toggle_bullet)
        numbered_btn.clicked.connect(self._toggle_numbered)
        layout.addWidget(bullet_btn)
        layout.addWidget(numbered_btn)
        layout.addWidget(_sep())

        # Image / Table / File attachment
        img_btn = _btn("🖼", "Insert image")
        img_btn.clicked.connect(self._insert_image)
        layout.addWidget(img_btn)

        tbl_btn = _btn("⊞", "Insert table")
        tbl_btn.clicked.connect(self._insert_table)
        layout.addWidget(tbl_btn)

        layout.addWidget(_sep())

        att_btn = _btn("📎", "Attach file")
        att_btn.clicked.connect(self._add_attachment)
        layout.addWidget(att_btn)

        layout.addStretch()
        return bar

    def _build_content(self) -> QWidget:
        pane = QWidget()
        pane.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(24, 16, 24, 8)
        layout.setSpacing(8)

        # Title — font-family intentionally NOT in QSS so setFont() works for font switching
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Title…")
        self._title_edit.setStyleSheet(
            f"QLineEdit {{ {self._input_ss()} font-size: 20px; font-weight: 700; }}"
            f"QLineEdit:focus {{ border-color: {'rgba(255,255,255,0.40)' if self._art_dark else '#FF6B35'}; }}"
        )
        # Font family set programmatically so _on_font_index_changed can override it
        self._title_edit.setFont(QFont("Marker Felt", _TITLE_FONT_SIZE, QFont.Weight.Bold))
        self._title_edit.installEventFilter(self)
        layout.addWidget(self._title_edit)

        # Rich-text WYSIWYG editor
        self._editor = QTextEdit()
        self._editor.setPlaceholderText(
            "Start writing…\n\n"
            "Use the toolbar above for Bold, Italic, lists, and font changes.\n"
            "Use 🖼 to embed images, ⊞ to insert a table, 📎 to attach files."
        )
        self._editor.setAcceptRichText(True)
        self._editor.setStyleSheet(
            f"QTextEdit {{ {self._input_ss()} }}"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(0,0,0,0.15); border-radius: 3px; }"
        )
        self._editor.currentCharFormatChanged.connect(self._sync_toolbar)
        self._editor.installEventFilter(self)
        layout.addWidget(self._editor, stretch=1)

        # ── Attachment chip bar (hidden when no attachments) ───────────────────
        self._att_panel = QWidget()
        self._att_panel.setStyleSheet("background: transparent;")
        self._att_layout = QHBoxLayout(self._att_panel)
        self._att_layout.setContentsMargins(0, 2, 0, 4)
        self._att_layout.setSpacing(6)
        att_icon_lbl = QLabel("📎")
        att_icon_lbl.setStyleSheet(
            f"font-size: 13px; color: {self._text_col()}; background: transparent;"
        )
        self._att_layout.addWidget(att_icon_lbl)
        self._att_layout.addStretch()
        self._att_panel.setVisible(False)
        layout.addWidget(self._att_panel)

        return pane

    def _build_bottom(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        if self._art_dark:
            bar.setStyleSheet(
                "background: rgba(0,0,0,0.25);"
                " border-top: 1px solid rgba(255,255,255,0.10);"
            )
        else:
            bar.setStyleSheet(
                "background: rgba(255,255,255,0.30);"
                " border-top: 1px solid rgba(0,0,0,0.08);"
            )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        # Word-style square color swatches — label prefix for clarity
        lbl = QPushButton("Label:")
        lbl.setEnabled(False)
        lbl.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; font-size: 11px;"
            f" color: {'rgba(200,180,155,0.80)' if self._art_dark else 'rgba(80,50,30,0.65)'}; }}"
        )
        layout.addWidget(lbl)
        layout.addSpacing(2)

        # NOT checkable — we manage visual state entirely in _pick_color.
        # _=False absorbs Qt's clicked(bool) arg so n/h keep their captured defaults.
        self._dot_btns: dict[str, QPushButton] = {}
        for name, hex_col in _COLOR_DOTS:
            dot = QPushButton("✓" if self._color_label == name else "")
            dot.setFixedSize(20, 20)
            dot.setToolTip(name.capitalize())
            dot.setStyleSheet(_dot_ss(hex_col, checked=(self._color_label == name)))
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            dot.clicked.connect(lambda _=False, n=name, h=hex_col: self._pick_color(n, h))
            self._dot_btns[name] = dot
            layout.addWidget(dot)

        layout.addStretch()

        # → Reminder convert
        convert_btn = QPushButton("→ Reminder")
        convert_btn.setFixedHeight(36)
        if self._art_dark:
            convert_btn.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.12);"
                " border: 1px solid rgba(255,255,255,0.25); border-radius: 9px;"
                " font-size: 12px; font-weight: 600;"
                " color: rgba(238,222,205,0.90); padding: 0 14px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.22); }"
            )
        else:
            convert_btn.setStyleSheet(
                "QPushButton { background: rgba(255,107,53,0.10);"
                " border: 1px solid rgba(255,107,53,0.30); border-radius: 9px;"
                " font-size: 12px; font-weight: 600; color: #FF6B35; padding: 0 14px; }"
                "QPushButton:hover { background: rgba(255,107,53,0.22); }"
            )
        convert_btn.clicked.connect(self._convert_to_reminder)
        layout.addWidget(convert_btn)

        # Cancel
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setMinimumWidth(80)
        if self._art_dark:
            cancel_btn.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.10);"
                " border: 1.5px solid rgba(255,255,255,0.22); border-radius: 9px;"
                " font-size: 13px; color: rgba(238,222,205,0.90); padding: 0 16px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.20); }"
            )
        else:
            cancel_btn.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.70);"
                " border: 1.5px solid rgba(0,0,0,0.15); border-radius: 9px;"
                " font-size: 13px; color: #2C0E00; padding: 0 16px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.90); }"
            )
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        # Save (primary)
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.setFixedHeight(36)
        save_btn.setMinimumWidth(80)
        save_btn.setStyleSheet(
            "QPushButton { background: #FF6B35; border: none; border-radius: 9px;"
            " font-size: 13px; font-weight: 700; color: white; padding: 0 20px; }"
            "QPushButton:hover   { background: #E85A25; }"
            "QPushButton:pressed { background: #D04A18; }"
        )
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        return bar

    # ── Focus tracking ────────────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.FocusIn:
            if obj is self._title_edit:
                self._last_text_focus = "title"
            elif obj is self._editor:
                self._last_text_focus = "editor"
        return super().eventFilter(obj, event)

    # ── Toolbar → editor sync ─────────────────────────────────────────────────

    def _sync_toolbar(self, fmt: QTextCharFormat) -> None:
        for widget, value in (
            (self._bold_btn,      fmt.fontWeight() >= QFont.Weight.Bold),
            (self._italic_btn,    fmt.fontItalic()),
            (self._underline_btn, fmt.fontUnderline()),
        ):
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)

        fname = fmt.font().family()
        if fname in _FONT_OPTIONS:
            for i in range(self._font_combo.model().rowCount()):
                item = self._font_combo.model().item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == fname:
                    self._font_combo.blockSignals(True)
                    self._font_combo.setCurrentIndex(i)
                    self._font_combo.blockSignals(False)
                    break

        size = fmt.fontPointSize()
        if size > 0:
            self._size_combo.blockSignals(True)
            self._size_combo.setCurrentText(str(int(size)))
            self._size_combo.blockSignals(False)

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _on_font_index_changed(self, idx: int) -> None:
        item = self._font_combo.model().item(idx)
        if item is None:
            return
        fname = item.data(Qt.ItemDataRole.UserRole)
        if not fname:
            return
        if self._last_text_focus == "title":
            # Apply to the whole title field (QLineEdit has no per-selection font)
            self._title_edit.setFont(QFont(fname, _TITLE_FONT_SIZE, QFont.Weight.Bold))
            self._title_edit.setFocus()
        else:
            # Applies to selected text (or cursor position for new typing)
            self._editor.setCurrentFont(QFont(fname))
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
            current.remove(cursor.block())   # actually detaches the block from the list
        else:
            fmt = QTextListFormat()
            fmt.setStyle(QTextListFormat.Style.ListDisc)
            cursor.createList(fmt)
        self._editor.setFocus()

    def _toggle_numbered(self) -> None:
        cursor  = self._editor.textCursor()
        current = cursor.currentList()
        if current and current.format().style() == QTextListFormat.Style.ListDecimal:
            current.remove(cursor.block())
        else:
            fmt = QTextListFormat()
            fmt.setStyle(QTextListFormat.Style.ListDecimal)
            cursor.createList(fmt)
        self._editor.setFocus()

    # ── Insert image ──────────────────────────────────────────────────────────

    def _insert_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Insert Image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"
        )
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Image Error", "Could not load the selected image.")
            return
        # Downscale wide images so they fit the editor without horizontal scroll
        if img.width() > 900:
            img = img.scaledToWidth(900, Qt.TransformationMode.SmoothTransformation)

        # Convert to PNG bytes via QBuffer → base64 → data URI embedded in HTML
        ba  = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenMode.WriteOnly)
        img.save(buf, "PNG")
        b64 = bytes(ba.toBase64()).decode()

        cursor = self._editor.textCursor()
        cursor.insertHtml(f'<img src="data:image/png;base64,{b64}" />')
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    # ── Insert table ──────────────────────────────────────────────────────────

    def _insert_table(self) -> None:
        dlg = _TableDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rows, cols = dlg.values()
        cursor = self._editor.textCursor()
        fmt = QTextTableFormat()
        fmt.setCellPadding(6)
        fmt.setCellSpacing(0)
        fmt.setBorder(1)
        fmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        cursor.insertTable(rows, cols, fmt)
        self._editor.setFocus()

    # ── File attachments ──────────────────────────────────────────────────────

    _MAX_ATT_BYTES = 2 * 1024 * 1024  # 2 MB per attachment

    def _add_attachment(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Attach File", "", "All Files (*)")
        if not path:
            return
        size = os.path.getsize(path)
        if size > self._MAX_ATT_BYTES:
            QMessageBox.warning(
                self, "File Too Large",
                f"Please attach files smaller than 2 MB.\n(Selected file: {size // 1024} KB)"
            )
            return
        with open(path, "rb") as fh:
            raw = fh.read()
        b64  = base64.b64encode(raw).decode()
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        name = os.path.basename(path)
        self._attachments.append({"name": name, "mime": mime, "data": b64})
        self._refresh_att_panel()

    def _open_attachment(self, att: dict) -> None:
        """Write attachment bytes to a temp file and open with the system viewer."""
        data   = base64.b64decode(att["data"])
        suffix = os.path.splitext(att["name"])[1] or ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            fh.write(data)
            tmp = fh.name
        QDesktopServices.openUrl(QUrl.fromLocalFile(tmp))

    def _remove_attachment(self, idx: int) -> None:
        if 0 <= idx < len(self._attachments):
            self._attachments.pop(idx)
            self._refresh_att_panel()

    def _make_att_chip(self, att: dict, idx: int) -> QWidget:
        chip = QFrame()
        if self._art_dark:
            chip.setStyleSheet(
                "QFrame { background: rgba(255,255,255,0.12);"
                " border: 1px solid rgba(255,255,255,0.20); border-radius: 10px; }"
            )
        else:
            chip.setStyleSheet(
                "QFrame { background: rgba(255,255,255,0.75);"
                " border: 1px solid rgba(0,0,0,0.15); border-radius: 10px; }"
            )
        row = QHBoxLayout(chip)
        row.setContentsMargins(8, 3, 5, 3)
        row.setSpacing(4)

        name_btn = QPushButton(att["name"])
        name_btn.setFlat(True)
        name_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        name_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; font-size: 11px;"
            f" color: {self._text_col()}; }}"
            f"QPushButton:hover {{ text-decoration: underline; }}"
        )
        name_btn.clicked.connect(lambda _=False, a=att: self._open_attachment(a))
        row.addWidget(name_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(14, 14)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " font-size: 10px; color: rgba(100,60,30,0.65); }"
            "QPushButton:hover { color: #EF4444; }"
        )
        del_btn.clicked.connect(lambda _=False, i=idx: self._remove_attachment(i))
        row.addWidget(del_btn)

        return chip

    def _refresh_att_panel(self) -> None:
        """Rebuild attachment chips: keep the 📎 label (index 0) and stretch (last)."""
        while self._att_layout.count() > 2:
            item = self._att_layout.takeAt(1)
            if item and item.widget():
                item.widget().deleteLater()

        for i, att in enumerate(self._attachments):
            # insertWidget(count-1, …) places each chip before the trailing stretch
            self._att_layout.insertWidget(self._att_layout.count() - 1,
                                          self._make_att_chip(att, i))

        self._att_panel.setVisible(bool(self._attachments))

    # ── Color dots ────────────────────────────────────────────────────────────

    def _pick_color(self, name: str, _hex: str) -> None:
        self._color_label = None if self._color_label == name else name
        for n, dot in self._dot_btns.items():
            h        = dict(_COLOR_DOTS)[n]
            selected = n == self._color_label
            dot.setText("✓" if selected else "")
            dot.setStyleSheet(_dot_ss(h, checked=selected))

    # ── Save / convert ────────────────────────────────────────────────────────

    def _save(self) -> None:
        title    = self._title_edit.text().strip()
        body     = self._editor.toHtml()
        att_json = json.dumps(self._attachments) if self._attachments else None

        if self._note is None:
            self._note_service.create_note(
                self._user.id,
                title=title,
                body_md=body,
                folder_id=self._folder_id,
                color_label=self._color_label,
                attachments=att_json,
            )
        else:
            self._note_service.update_note(
                self._note.id,
                title=title,
                body_md=body,
                color_label=self._color_label,
                attachments=att_json,
            )
        self.note_saved.emit()
        self.accept()

    def _convert_to_reminder(self) -> None:
        from remindee.ui.reminder_dialog import ReminderDialog
        scheduler = getattr(self.parent(), "_scheduler", None)
        if scheduler is None:
            QMessageBox.warning(self, "Cannot Convert",
                                "Scheduler is not available in this context.")
            return
        dlg = ReminderDialog(
            self._user, scheduler,
            prefill_name=self._title_edit.text().strip() or "Untitled",
            parent=self,
        )
        if dlg.exec():
            self.accept()
