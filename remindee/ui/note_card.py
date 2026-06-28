from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# color_label string → hex
_COLOR_STRIP: dict[str, str] = {
    "orange": "#FF6B35",
    "red":    "#EF4444",
    "green":  "#22C55E",
    "blue":   "#3B82F6",
    "purple": "#A855F7",
}


class NoteCard(QWidget):
    """Compact note entry card for the notes sidebar list."""

    clicked          = Signal(int)   # note_id
    delete_requested = Signal(int)   # note_id
    pin_requested    = Signal(int)   # note_id

    def __init__(
        self,
        note_id: int,
        title: str,
        body_preview: str,
        is_pinned: bool = False,
        color_label: str | None = None,
        selected: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._note_id    = note_id
        self._is_pinned  = is_pinned
        self._color_hex  = _COLOR_STRIP.get(color_label or "", "")
        self._selected   = selected
        self._hovered    = False

        self.setObjectName("NoteCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(76)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._build(title, body_preview)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self, title: str, body_preview: str) -> None:
        # The left color strip is 4 px wide, handled in paintEvent.
        # Content sits 12 px from the left (4 strip + 8 gap).
        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 8, 10, 8)
        outer.setSpacing(0)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        self._title_lbl = QLabel(title or "Untitled")
        self._title_lbl.setObjectName("NoteCardTitle")
        self._title_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 700; background: transparent; border: none;"
        )
        self._title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._preview_lbl = QLabel(body_preview or "")
        self._preview_lbl.setObjectName("NoteCardPreview")
        self._preview_lbl.setStyleSheet(
            "font-size: 11px; background: transparent; border: none;"
        )
        self._preview_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        text_col.addWidget(self._title_lbl)
        text_col.addWidget(self._preview_lbl)

        outer.addLayout(text_col, stretch=1)

        self._pin_lbl = QLabel("📌")
        self._pin_lbl.setObjectName("NoteCardPin")
        self._pin_lbl.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        self._pin_lbl.setVisible(self._is_pinned)
        self._pin_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        outer.addWidget(self._pin_lbl, alignment=Qt.AlignmentFlag.AlignTop)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update()

    def set_pinned(self, pinned: bool) -> None:
        self._is_pinned = pinned
        self._pin_lbl.setVisible(pinned)

    def note_id(self) -> int:
        return self._note_id

    # ── Events ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._note_id)
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        pin_text = "Unpin" if self._is_pinned else "Pin"
        pin_action = menu.addAction(pin_text)
        menu.addSeparator()
        del_action = menu.addAction("Delete")
        action = menu.exec(self.mapToGlobal(pos))
        if action == pin_action:
            self.pin_requested.emit(self._note_id)
        elif action == del_action:
            self.delete_requested.emit(self._note_id)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()

        # Selection / hover tint — drawn as the card background.
        # We let QSS handle the base background via objectName "NoteCard",
        # but we add a subtle overlay here for hover/selection.
        if self._selected:
            p.fillRect(rect, QColor(255, 107, 53, 28))
            p.setPen(QPen(QColor(255, 107, 53, 120), 1))
            p.drawRect(rect.adjusted(0, 0, -1, -1))
        elif self._hovered:
            p.fillRect(rect, QColor(255, 107, 53, 12))

        # Left color strip
        if self._color_hex:
            strip_color = QColor(self._color_hex)
            p.fillRect(0, 0, 4, rect.height(), strip_color)
        else:
            # Transparent placeholder — just a subtle border
            p.fillRect(0, 0, 4, rect.height(), QColor(0, 0, 0, 0))

        p.end()
