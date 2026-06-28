from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from remindee.models.note import Note
from remindee.ui.note_card import NoteCard


class NoteListWidget(QWidget):
    """Scrollable list of NoteCard widgets with a search bar at top."""

    note_selected     = Signal(int)   # note_id
    new_note_requested = Signal()
    search_changed    = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NoteListWidget")

        self._cards: dict[int, NoteCard] = {}   # note_id → card
        self._selected_id: int | None = None

        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header row: title + (search is below) ────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(12, 12, 12, 6)

        title_lbl = QLabel("Notes")
        title_lbl.setObjectName("NoteListTitle")
        title_lbl.setStyleSheet(
            "font-size: 16px; font-weight: 700; background: transparent;"
        )
        header.addWidget(title_lbl)
        header.addStretch()
        root.addLayout(header)

        # ── Search bar ────────────────────────────────────────────────────────
        self._search = QLineEdit()
        self._search.setObjectName("NoteSearch")
        self._search.setPlaceholderText("🔍  Search notes…")
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(
            "QLineEdit#NoteSearch {"
            " background: rgba(255,107,53,0.07);"
            " border: 1px solid rgba(255,107,53,0.18);"
            " border-radius: 8px;"
            " font-size: 13px;"
            " padding: 7px 10px;"
            " margin: 0 10px 6px 10px;"
            "}"
            "QLineEdit#NoteSearch:focus { border-color: #FF6B35; }"
        )
        self._search.textChanged.connect(self.search_changed)
        root.addWidget(self._search)

        # ── Scroll area ───────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setObjectName("NoteScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(scroll.Shape.NoFrame)

        self._container = QWidget()
        self._container.setObjectName("NoteListContainer")
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(1)
        self._list_layout.addStretch()

        scroll.setWidget(self._container)
        root.addWidget(scroll, stretch=1)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_notes(self, notes: list[Note]) -> None:
        """Replace all cards. Pinned notes sort to the top."""
        # Clear existing cards
        for card in self._cards.values():
            self._list_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._selected_id = None

        # Sort: pinned DESC, updated_at DESC
        sorted_notes = sorted(
            notes,
            key=lambda n: (not n.is_pinned, -(n.updated_at.timestamp() if n.updated_at else 0)),
        )

        # Insert before the trailing stretch (last item)
        insert_pos = self._list_layout.count() - 1
        for note in sorted_notes:
            preview = _first_line(note.body_md or "")
            card = NoteCard(
                note_id=note.id,
                title=note.title or "Untitled",
                body_preview=preview,
                is_pinned=note.is_pinned,
                color_label=note.color_label,
                selected=False,
                parent=self._container,
            )
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.clicked.connect(self._on_card_clicked)
            card.delete_requested.connect(self._forward_delete)
            self._list_layout.insertWidget(insert_pos, card)
            insert_pos += 1
            self._cards[note.id] = card

    def select_note(self, note_id: int | None) -> None:
        """Highlight the card for note_id; deselect all others."""
        if self._selected_id is not None and self._selected_id in self._cards:
            self._cards[self._selected_id].set_selected(False)
        self._selected_id = note_id
        if note_id is not None and note_id in self._cards:
            self._cards[note_id].set_selected(True)

    def get_selected_id(self) -> int | None:
        return self._selected_id

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_card_clicked(self, note_id: int) -> None:
        self.select_note(note_id)
        self.note_selected.emit(note_id)

    def _forward_delete(self, note_id: int) -> None:
        # Remove the card optimistically; the integrator should connect the card's
        # delete_requested signal directly for service-layer calls.
        card = self._cards.pop(note_id, None)
        if card:
            self._list_layout.removeWidget(card)
            card.deleteLater()
        if self._selected_id == note_id:
            self._selected_id = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _first_line(text: str) -> str:
    """Return the first non-empty line of text, stripped of Markdown markers."""
    import re
    for line in text.splitlines():
        stripped = re.sub(r"^#{1,6}\s*|^\s*[-*+]\s+|^\s*>\s*|^\*{1,3}|_{1,3}", "", line).strip()
        if stripped:
            return stripped
    return ""
