from __future__ import annotations

import random
from datetime import datetime

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy, QVBoxLayout,
)

from remindee.models.note import Note
from remindee.ui.reminder_card import (
    _DARK_BASES, _DARK_BTN, _SCHEMES, _STYLES,
    _OutlinedLabel, _draw_base, _draw_grain,
)

_COLOR_HEX: dict[str, str] = {
    "orange": "#FF6B35",
    "red":    "#EF4444",
    "green":  "#22C55E",
    "blue":   "#3B82F6",
    "purple": "#A855F7",
}


def _first_line(content: str) -> str:
    """Return the first non-empty line of note content, stripping HTML or markdown."""
    import re
    text = content.strip()
    if text.startswith("<"):
        # Remove <style>…</style> blocks first so CSS text doesn't appear in preview
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Strip remaining HTML tags and decode entities
        text = re.sub(r"<[^>]+>", " ", text)
        text = (text.replace("&amp;", "&").replace("&lt;", "<")
                    .replace("&gt;", ">").replace("&nbsp;", " ").replace("&#160;", " "))
    else:
        # Legacy markdown: strip syntax
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"(\*{1,3}|_{1,3})(.*?)\1", r"\2", text)
        text = re.sub(r"`([^`]*)`", r"\1", text)
    for line in text.splitlines():
        line = " ".join(line.split())
        if line and not line.startswith("<!"):
            return line
    return ""


class NoteCard(QFrame):
    """Full-width note card with procedural art — mirrors ReminderCard style."""

    edit_requested   = Signal(object)   # Note
    delete_requested = Signal(object)   # Note
    pin_requested    = Signal(object)   # Note

    def __init__(self, note: Note, parent=None) -> None:
        super().__init__(parent)
        self._note    = note
        self._hovered = False

        self._seed    = (note.id or abs(hash(note.title or ""))) & 0x7FFFFFFF
        self._is_dark = (self._seed * 11 + 5) % 5 == 0

        self.setObjectName("NoteCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumHeight(72)
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        if self._note.is_pinned:
            pin_lbl = QLabel("📌")
            pin_lbl.setStyleSheet("font-size: 13px; background: transparent;")
            top_row.addWidget(pin_lbl)

        title_text = self._note.title or "Untitled"
        title = _OutlinedLabel(title_text)
        title.setObjectName("CardTitle")
        title.setFont(QFont("Marker Felt", 14))
        top_row.addWidget(title, stretch=1)

        if self._note.attachments:
            import json as _json
            try:
                if _json.loads(self._note.attachments):
                    att_lbl = QLabel("📎")
                    att_lbl.setStyleSheet("background: transparent; font-size: 11px;")
                    top_row.addWidget(att_lbl)
            except Exception:
                pass

        edit_btn = QPushButton("✏")
        edit_btn.setObjectName("CardActionBtn")
        edit_btn.setFixedSize(38, 38)
        edit_btn.setToolTip("Edit note")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._note))
        top_row.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("CardActionBtn")
        del_btn.setFixedSize(38, 38)
        del_btn.setToolTip("Delete note")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._note))
        top_row.addWidget(del_btn)

        outer.addLayout(top_row)

        if self._note.body_md:
            preview = _first_line(self._note.body_md)
            if preview:
                det = _OutlinedLabel(preview[:120])
                det.setObjectName("CardDetails")
                det.setWordWrap(True)
                outer.addWidget(det)

        # Timestamp line
        time_str = self._format_time()
        if time_str:
            trig = _OutlinedLabel(time_str)
            trig.setObjectName("CardTrigger")
            outer.addWidget(trig)

        if self._is_dark:
            for btn in (edit_btn, del_btn):
                btn.setStyleSheet(_DARK_BTN)

    def _format_time(self) -> str:
        ts = self._note.updated_at or self._note.created_at
        if ts is None:
            return ""
        secs = int((datetime.utcnow() - ts).total_seconds())
        if secs < 60:
            return "Just now"
        if secs < 3600:
            return f"Updated {secs // 60}m ago"
        if secs < 86400:
            return f"Updated {secs // 3600}h ago"
        return f"Updated {ts.strftime('%b %d')}"

    # ── Events ────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        self.edit_requested.emit(self._note)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def _show_context_menu(self, global_pos) -> None:
        menu = QMenu(self)
        pin_text = "Unpin" if self._note.is_pinned else "Pin"
        pin_action = menu.addAction(pin_text)
        menu.addSeparator()
        del_action = menu.addAction("Delete")
        action = menu.exec(global_pos)
        if action == pin_action:
            self.pin_requested.emit(self._note)
        elif action == del_action:
            self.delete_requested.emit(self._note)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    # ── Painting ─────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r      = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = 14.0

        clip = QPainterPath()
        clip.addRoundedRect(r, radius, radius)
        p.setClipPath(clip)

        if self._is_dark:
            p.fillRect(self.rect(), _DARK_BASES[self._seed % len(_DARK_BASES)])
        else:
            p.fillRect(self.rect(), QColor(255, 255, 255))

        self._paint_art(p, r)

        veil = QColor(0, 0, 0, 55) if self._is_dark else QColor(255, 255, 255, 72)
        p.fillPath(clip, veil)

        # Color-label strip — 7 px left edge, visible after color is set in NoteDialog
        if self._note.color_label and self._note.color_label in _COLOR_HEX:
            strip = QColor(_COLOR_HEX[self._note.color_label])
            strip.setAlpha(215)
            p.fillRect(0, 0, 7, self.height(), strip)

        p.setClipping(False)
        border_alpha = 220 if self._hovered else (110 if self._is_dark else 70)
        border_col = (QColor(255, 145, 90, border_alpha) if self._is_dark
                      else QColor(255, 107, 53, border_alpha))
        p.setPen(QPen(border_col, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, radius, radius)

    def _paint_art(self, p: QPainter, rect: QRectF) -> None:
        rng     = random.Random(self._seed)
        palette = _SCHEMES[self._seed % len(_SCHEMES)]
        style   = (self._seed * 17 + 5) % len(_STYLES)

        if not self._is_dark:
            _draw_base(p, rect, rng, palette, self._seed)

        _STYLES[style](p, rect, rng, palette)

        if (self._seed * 3 + 1) % 5 < 2:
            _draw_grain(p, rect, rng)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self, note: Note) -> None:
        self._note    = note
        self._seed    = (note.id or abs(hash(note.title or ""))) & 0x7FFFFFFF
        self._is_dark = (self._seed * 11 + 5) % 5 == 0
        old = self.layout()
        if old:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            old.deleteLater()
        self._build()
        self.update()
