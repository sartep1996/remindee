from __future__ import annotations

import math
import random
from datetime import datetime

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPainterPath,
    QPen, QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
)

from remindee.models.reminder import Reminder, FrequencyType

_FREQ_LABELS = {
    FrequencyType.OFTEN:    "Every hour",
    FrequencyType.MEDIUM:   "Every 6h",
    FrequencyType.RARELY:   "Daily",
    FrequencyType.RANDOM:   "Random",
    FrequencyType.SPECIFIC: "One-time",
}

# ── Art palette ───────────────────────────────────────────────────────────────

_SCHEMES = [
    (QColor(255,  40,  10), QColor(255, 195,  30)),  # 0 fire
    (QColor( 25,  65, 240), QColor( 40, 200, 255)),  # 1 ocean
    (QColor(170,  15, 215), QColor(255,  55, 200)),  # 2 cosmos
    (QColor(  5, 175,  70), QColor( 35, 245, 160)),  # 3 nature
    (QColor(255, 145,   0), QColor(225,  35,  75)),  # 4 sunset
    (QColor(  0, 170, 215), QColor( 20,  50, 205)),  # 5 teal
    (QColor(225,  20,  70), QColor(255, 110, 195)),  # 6 rose
    (QColor( 70, 205,  10), QColor( 10, 110, 215)),  # 7 lime
]

# Dark bases paired to each scheme
_DARK_BASES = [
    QColor( 22,  6,  2),   # 0 charcoal-red
    QColor(  3,  8, 28),   # 1 deep navy
    QColor( 16,  3, 24),   # 2 deep purple
    QColor(  2, 18,  8),   # 3 forest black
    QColor( 22,  8,  2),   # 4 dark amber
    QColor(  2, 14, 22),   # 5 dark teal
    QColor( 20,  3, 12),   # 6 dark rose
    QColor(  5, 18,  2),   # 7 dark lime
]


def _c(col: QColor, alpha: int) -> QColor:
    return QColor(col.red(), col.green(), col.blue(), max(0, min(255, alpha)))


# ── 8 primary style functions — each is aggressively distinct ─────────────────

def _style_mega_blob(p, rect, rng, A, B):
    """One enormous soft blob, off-centre, covers 70-90% of the card."""
    w, h = rect.width(), rect.height()
    side = rng.randint(0, 3)  # 0=left 1=right 2=top 3=bottom
    cx = (rect.x() + rng.uniform(-0.05, 0.25) * w if side == 0 else
          rect.x() + rng.uniform(0.75, 1.05) * w if side == 1 else
          rect.x() + rng.uniform(0.3, 0.7) * w)
    cy = (rect.y() + rng.uniform(0.3, 0.7) * h if side < 2 else
          rect.y() + rng.uniform(-0.1, 0.25) * h if side == 2 else
          rect.y() + rng.uniform(0.75, 1.1) * h)
    r   = rng.uniform(0.7, 1.15) * max(w, h)
    col = A if rng.random() < 0.55 else B
    g   = QRadialGradient(QPointF(cx, cy), r)
    g.setColorAt(0.0, _c(col, rng.randint(200, 245)))
    g.setColorAt(0.55, _c(col, rng.randint(100, 160)))
    g.setColorAt(1.0, _c(col, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), r, r)
    # Second smaller contrasting blob
    cx2 = rect.x() + rng.uniform(0.6, 1.0) * w
    cy2 = rect.y() + rng.uniform(0.0, 0.5) * h
    r2  = rng.uniform(0.25, 0.5) * h
    g2  = QRadialGradient(QPointF(cx2, cy2), r2)
    g2.setColorAt(0.0, _c(B, rng.randint(170, 220)))
    g2.setColorAt(1.0, _c(B, 0))
    p.setBrush(QBrush(g2))
    p.drawEllipse(QPointF(cx2, cy2), r2, r2)


def _style_parallel_lines(p, rect, rng, A, B):
    """3-5 thick parallel diagonal lines — racing stripes."""
    w, h = rect.width(), rect.height()
    n     = rng.randint(3, 5)
    thick = rng.uniform(14, 32)
    slope = rng.uniform(-0.6, 0.6)
    col   = A if rng.random() < 0.5 else B
    col2  = B if col is A else A
    p.setBrush(Qt.NoBrush)
    for i in range(n):
        t  = (i + 0.5) / n
        y0 = rect.y() + t * h
        x1 = rect.x() - 0.05 * w
        y1 = y0
        x2 = rect.x() + 1.05 * w
        y2 = y0 + slope * w
        c  = col if i % 2 == 0 else col2
        pen = QPen(_c(c, rng.randint(190, 235)), thick, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _style_big_rect(p, rect, rng, A, B):
    """1-2 large solid rectangles — bold hard geometry."""
    w, h = rect.width(), rect.height()
    p.setPen(Qt.NoPen)
    for i in range(rng.randint(1, 2)):
        if rng.random() < 0.5:
            # Tall thin slab — left or right
            x_off = rng.uniform(-0.05, 0.6) * w
            rw    = rng.uniform(0.2, 0.45) * w
            rh    = rng.uniform(0.7, 1.2) * h
            ry    = rect.y() + rng.uniform(-0.1, 0.2) * h
        else:
            # Wide flat bar — top or bottom
            x_off = rect.x() + rng.uniform(-0.1, 0.0) * w
            rw    = rng.uniform(0.8, 1.2) * w
            rh    = rng.uniform(0.2, 0.5) * h
            ry    = rect.y() + rng.uniform(0, 0.7) * h
        col  = A if i == 0 else B
        cr   = rng.uniform(0, 14)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect.x() + x_off, ry, rw, rh), cr, cr)
        p.setBrush(_c(col, rng.randint(175, 230)))
        p.drawPath(path)


def _style_corner_wedge(p, rect, rng, A, B):
    """Solid quarter-circle wedge from a random corner — huge, hard-edged."""
    w, h = rect.width(), rect.height()
    corner = rng.randint(0, 3)
    cx = rect.x() + (0 if corner in (0, 2) else w)
    cy = rect.y() + (0 if corner in (0, 1) else h)
    r  = rng.uniform(0.7, 1.1) * max(w, h)
    starts = [0, 270, 90, 180]
    col = A if rng.random() < 0.5 else B
    path = QPainterPath()
    path.moveTo(cx, cy)
    path.arcTo(QRectF(cx - r, cy - r, r * 2, r * 2), starts[corner], 90)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(_c(col, rng.randint(200, 245)))
    p.drawPath(path)
    # Small contrasting wedge from another corner
    corner2 = (corner + 2) % 4
    cx2 = rect.x() + (0 if corner2 in (0, 2) else w)
    cy2 = rect.y() + (0 if corner2 in (0, 1) else h)
    r2  = rng.uniform(0.2, 0.45) * max(w, h)
    path2 = QPainterPath()
    path2.moveTo(cx2, cy2)
    path2.arcTo(QRectF(cx2 - r2, cy2 - r2, r2 * 2, r2 * 2), starts[corner2], 90)
    path2.closeSubpath()
    p.setBrush(_c(B if col is A else A, rng.randint(160, 210)))
    p.drawPath(path2)


def _style_triangle(p, rect, rng, A, B):
    """Large filled triangle(s) — sharp, dramatic, covers most of card."""
    w, h = rect.width(), rect.height()
    ox, oy = rect.x(), rect.y()
    variant = rng.randint(0, 3)
    # Fixed-edge triangles that fill a significant portion of the card
    triangles = [
        ([QPointF(ox, oy), QPointF(ox + w, oy), QPointF(ox, oy + h)], A, 210),
        ([QPointF(ox + w, oy), QPointF(ox + w, oy + h), QPointF(ox, oy + h)], B, 180),
    ] if variant == 0 else [
        ([QPointF(ox, oy), QPointF(ox + w * 0.55, oy), QPointF(ox, oy + h)], A, 210),
        ([QPointF(ox + w * 0.45, oy + h), QPointF(ox + w, oy + h), QPointF(ox + w, oy)], B, 180),
    ] if variant == 1 else [
        ([QPointF(ox + w * 0.5, oy - h * 0.1), QPointF(ox - w * 0.1, oy + h * 1.1),
          QPointF(ox + w * 1.1, oy + h * 1.1)], A, 215),
    ] if variant == 2 else [
        ([QPointF(ox, oy + h * 0.5), QPointF(ox + w, oy), QPointF(ox + w, oy + h)], A, 200),
        ([QPointF(ox, oy), QPointF(ox + w * 0.5, oy), QPointF(ox, oy + h * 0.5)], B, 170),
    ]
    p.setPen(Qt.NoPen)
    for pts, col, alpha in triangles:
        path = QPainterPath()
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
        p.setBrush(_c(col, alpha))
        p.drawPath(path)


def _style_diagonal_split(p, rect, rng, A, B):
    """Card hard-split diagonally into two solid halves — bold graphic design."""
    w, h = rect.width(), rect.height()
    ox, oy = rect.x(), rect.y()
    variant = rng.randint(0, 3)
    if variant == 0:
        # Main diagonal: top-left triangle A, bottom-right B
        pts_a = [QPointF(ox, oy), QPointF(ox + w, oy), QPointF(ox, oy + h)]
        pts_b = [QPointF(ox + w, oy), QPointF(ox + w, oy + h), QPointF(ox, oy + h)]
    elif variant == 1:
        # Anti-diagonal: top-right A, bottom-left B
        pts_a = [QPointF(ox, oy), QPointF(ox + w, oy), QPointF(ox + w, oy + h)]
        pts_b = [QPointF(ox, oy), QPointF(ox + w, oy + h), QPointF(ox, oy + h)]
    elif variant == 2:
        # Steep diagonal — cuts at ~30/70 split
        pts_a = [QPointF(ox, oy), QPointF(ox + w * 0.35, oy), QPointF(ox, oy + h)]
        pts_b = [QPointF(ox + w * 0.35, oy), QPointF(ox + w, oy),
                 QPointF(ox + w, oy + h), QPointF(ox, oy + h)]
    else:
        # Horizontal split with diagonal cut
        pts_a = [QPointF(ox, oy), QPointF(ox + w, oy),
                 QPointF(ox + w, oy + h * 0.4), QPointF(ox, oy + h * 0.6)]
        pts_b = [QPointF(ox, oy + h * 0.6), QPointF(ox + w, oy + h * 0.4),
                 QPointF(ox + w, oy + h), QPointF(ox, oy + h)]
    p.setPen(Qt.NoPen)
    for pts, col, alpha in [(pts_a, A, 220), (pts_b, B, 200)]:
        path = QPainterPath()
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
        p.setBrush(_c(col, alpha))
        p.drawPath(path)


def _style_dot_field(p, rect, rng, A, B):
    """8-14 large solid circles scattered across the card — vivid dot pattern."""
    w, h = rect.width(), rect.height()
    n = rng.randint(8, 14)
    p.setPen(Qt.NoPen)
    for i in range(n):
        cx = rect.x() + rng.uniform(-0.05, 1.05) * w
        cy = rect.y() + rng.uniform(-0.1, 1.1) * h
        r  = rng.uniform(0.06, 0.18) * h
        col = A if i % 2 == 0 else B
        p.setBrush(_c(col, rng.randint(175, 230)))
        p.drawEllipse(QPointF(cx, cy), r, r)


def _style_ring(p, rect, rng, A, B):
    """1-2 large rings — crisp geometric circles with thick bands."""
    w, h = rect.width(), rect.height()
    p.setPen(Qt.NoPen)
    configs = [
        (rect.x() + rng.uniform(0.1, 0.5) * w,
         rect.y() + rng.uniform(0.1, 0.9) * h,
         rng.uniform(0.45, 0.9) * h,
         rng.uniform(0.4, 0.65),
         A),
    ]
    if rng.random() < 0.6:
        configs.append((
            rect.x() + rng.uniform(0.5, 0.95) * w,
            rect.y() + rng.uniform(0.1, 0.9) * h,
            rng.uniform(0.25, 0.55) * h,
            rng.uniform(0.3, 0.55),
            B,
        ))
    for cx, cy, outer, inner_ratio, col in configs:
        inner = outer * inner_ratio
        outer_p = QPainterPath()
        outer_p.addEllipse(QPointF(cx, cy), outer, outer)
        inner_p = QPainterPath()
        inner_p.addEllipse(QPointF(cx, cy), inner, inner)
        ring = outer_p.subtracted(inner_p)
        p.setBrush(_c(col, rng.randint(185, 240)))
        p.drawPath(ring)


_STYLES = [
    _style_mega_blob,
    _style_parallel_lines,
    _style_big_rect,
    _style_corner_wedge,
    _style_triangle,
    _style_diagonal_split,
    _style_dot_field,
    _style_ring,
]


# ── Card widget ───────────────────────────────────────────────────────────────

_DARK_TEXT   = QColor(238, 222, 205)
_DARK_TEXT2  = QColor(190, 165, 140)
_DARK_BTN    = (
    "QPushButton{background:transparent;border:none;border-radius:6px;"
    "color:rgba(230,210,190,0.85);font-size:15px;padding:4px 6px;}"
    "QPushButton:hover{background:rgba(255,255,255,0.14);color:white;}"
)
_DARK_BADGE  = (
    "background:rgba(255,255,255,0.12);color:rgba(230,215,195,0.9);"
    "border:1px solid rgba(255,255,255,0.18);border-radius:6px;"
    "padding:2px 9px;font-size:10px;font-weight:700;"
)


class ReminderCard(QFrame):
    edit_requested   = Signal(object)
    done_requested   = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, reminder: Reminder, parent=None) -> None:
        super().__init__(parent)
        self._reminder = reminder
        self._hovered  = False

        seed = (reminder.id or abs(hash(reminder.name))) & 0x7FFFFFFF
        self._seed    = seed
        self._is_dark = (seed * 11 + 5) % 5 == 0   # ~20% of cards are dark

        self.setObjectName("ReminderCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumHeight(72)
        self._build()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        title = QLabel(self._reminder.name)
        title.setObjectName("CardTitle")
        top_row.addWidget(title, stretch=1)

        freq_badge = QLabel(_FREQ_LABELS.get(self._reminder.frequency, ""))
        freq_badge.setObjectName("FreqBadge")
        top_row.addWidget(freq_badge)

        edit_btn = QPushButton("✏")
        edit_btn.setObjectName("CardActionBtn")
        edit_btn.setFixedSize(30, 30)
        edit_btn.setToolTip("Edit")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._reminder))
        top_row.addWidget(edit_btn)

        done_btn = QPushButton("✓")
        done_btn.setObjectName("CardActionBtn")
        done_btn.setFixedSize(30, 30)
        done_btn.setToolTip("Mark Done")
        done_btn.clicked.connect(lambda: self.done_requested.emit(self._reminder))
        top_row.addWidget(done_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("CardActionBtn")
        del_btn.setFixedSize(30, 30)
        del_btn.setToolTip("Delete")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._reminder))
        top_row.addWidget(del_btn)

        outer.addLayout(top_row)

        det = None
        if self._reminder.details:
            det = QLabel(self._reminder.details[:120])
            det.setObjectName("CardDetails")
            det.setWordWrap(True)
            outer.addWidget(det)

        trig = None
        trigger_text = self._format_trigger()
        if trigger_text:
            trig = QLabel(trigger_text)
            trig.setObjectName("CardTrigger")
            outer.addWidget(trig)

        if self._is_dark:
            # Override text to light colours so labels are readable on dark bg
            pal = title.palette()
            pal.setColor(pal.ColorRole.WindowText, _DARK_TEXT)
            title.setPalette(pal)

            for widget in [det, trig]:
                if widget is None:
                    continue
                pal2 = widget.palette()
                pal2.setColor(pal2.ColorRole.WindowText, _DARK_TEXT2)
                widget.setPalette(pal2)

            freq_badge.setStyleSheet(_DARK_BADGE)
            for btn in (edit_btn, done_btn, del_btn):
                btn.setStyleSheet(_DARK_BTN)

    def _format_trigger(self) -> str:
        if self._reminder.frequency == FrequencyType.SPECIFIC and self._reminder.specific_datetime:
            dt = self._reminder.specific_datetime
            return f"Due: {dt.strftime('%b %d, %Y  %H:%M')}"
        if self._reminder.next_trigger:
            dt   = self._reminder.next_trigger
            secs = int((dt - datetime.utcnow()).total_seconds())
            if secs < 0:     return "Overdue"
            if secs < 3600:  return f"Next: {secs // 60}m"
            if secs < 86400: return f"Next: {secs // 3600}h"
            return f"Next: {dt.strftime('%b %d')}"
        return ""

    # ── Hover ────────────────────────────────────────────────────────────────

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r      = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = 14.0

        clip = QPainterPath()
        clip.addRoundedRect(r, radius, radius)
        p.setClipPath(clip)

        # Background
        if self._is_dark:
            p.fillRect(self.rect(), _DARK_BASES[self._seed % 8])
        else:
            p.fillRect(self.rect(), QColor(255, 255, 255))

        # Art
        self._paint_art(p, r)

        # Frosted veil — light on bright cards, subtle dark on dark cards
        veil = QColor(0, 0, 0, 55) if self._is_dark else QColor(255, 255, 255, 72)
        p.fillPath(clip, veil)

        # Border
        p.setClipping(False)
        border_alpha = 220 if self._hovered else (100 if self._is_dark else 70)
        border_col   = (QColor(255, 140, 80, border_alpha) if self._is_dark
                        else QColor(255, 107, 53, border_alpha))
        p.setPen(QPen(border_col, 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, radius, radius)
        p.end()

    def _paint_art(self, p: QPainter, rect: QRectF) -> None:
        rng   = random.Random(self._seed)
        A, B  = _SCHEMES[self._seed % 8]
        style = (self._seed * 17 + 5) % len(_STYLES)

        # Light cards may have a tinted base gradient
        if not self._is_dark:
            base = self._seed % 3
            if base == 0:
                p.fillRect(rect, _c(A, 28))
            elif base == 1:
                g = QLinearGradient(
                    rect.bottomLeft() if self._seed % 2 else rect.topLeft(),
                    rect.topRight()   if self._seed % 2 else rect.bottomRight()
                )
                g.setColorAt(0.0, _c(A, 50))
                g.setColorAt(1.0, _c(B, 38))
                p.fillRect(rect, QBrush(g))

        # Primary style — large and dominant
        _STYLES[style](p, rect, rng, A, B)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self, reminder: Reminder) -> None:
        self._reminder = reminder
        old = self.layout()
        if old:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            old.deleteLater()
        self._build()
