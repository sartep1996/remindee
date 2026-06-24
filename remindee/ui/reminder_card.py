from __future__ import annotations

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

# Eight high-saturation (primary, secondary) colour pairs.
_SCHEMES = [
    (QColor(255,  55,  20), QColor(255, 195,  40)),  # 0 fire
    (QColor( 35,  70, 230), QColor( 55, 200, 255)),  # 1 ocean
    (QColor(175,  20, 215), QColor(255,  65, 200)),  # 2 cosmos
    (QColor( 10, 175,  75), QColor( 45, 240, 165)),  # 3 nature
    (QColor(255, 150,   0), QColor(225,  45,  80)),  # 4 sunset
    (QColor(  0, 175, 210), QColor( 25,  55, 200)),  # 5 teal
    (QColor(225,  25,  75), QColor(255, 115, 195)),  # 6 rose
    (QColor( 75, 200,  15), QColor( 15, 115, 210)),  # 7 lime
]

# Weighted element menu — each entry is (type_key, weight).
# Higher weight = appears more often, but every type CAN appear on any card.
_MENU = [
    ("blob",     3),
    ("rect",     3),
    ("line",     3),
    ("corner",   2),
    ("triangle", 2),
    ("stripe",   2),
    ("dots",     2),
    ("ring",     1),
]
_TYPES   = [t for t, _ in _MENU]
_WEIGHTS = [w for _, w in _MENU]


def _c(col: QColor, alpha: int) -> QColor:
    return QColor(col.red(), col.green(), col.blue(), alpha)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red()   * (1 - t) + b.red()   * t),
        int(a.green() * (1 - t) + b.green() * t),
        int(a.blue()  * (1 - t) + b.blue()  * t),
    )


# ── Element draw functions ────────────────────────────────────────────────────

def _draw_blob(p: QPainter, rect: QRectF, rng: random.Random,
               col: QColor, alpha: int) -> None:
    """Radial gradient circle — soft, organic."""
    w, h = rect.width(), rect.height()
    cx = rect.x() + rng.uniform(-0.15, 1.15) * w
    cy = rect.y() + rng.uniform(-0.15, 1.15) * h
    r  = rng.uniform(0.25, 1.1) * h
    g  = QRadialGradient(QPointF(cx, cy), r)
    g.setColorAt(0.0, _c(col, alpha))
    g.setColorAt(1.0, _c(col, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), r, r)


def _draw_rect(p: QPainter, rect: QRectF, rng: random.Random,
               col: QColor, alpha: int) -> None:
    """Filled rounded-rectangle — hard geometry."""
    w, h = rect.width(), rect.height()
    rx = rect.x() + rng.uniform(-0.1, 0.7) * w
    ry = rect.y() + rng.uniform(-0.1, 0.7) * h
    rw = rng.uniform(0.15, 0.7) * w
    rh = rng.uniform(0.3,  1.3) * h
    corner_r = rng.uniform(0, 18)
    path = QPainterPath()
    path.addRoundedRect(QRectF(rx, ry, rw, rh), corner_r, corner_r)
    p.setPen(Qt.NoPen)
    p.setBrush(_c(col, alpha))
    p.drawPath(path)


def _draw_line(p: QPainter, rect: QRectF, rng: random.Random,
               col: QColor, alpha: int) -> None:
    """Thick straight line — bold, graphic."""
    w, h = rect.width(), rect.height()
    # Lines always cross most of the card width for visual impact
    x1 = rect.x() + rng.uniform(-0.05, 0.2) * w
    y1 = rect.y() + rng.uniform(-0.3, 1.3) * h
    x2 = rect.x() + rng.uniform(0.8, 1.05) * w
    y2 = rect.y() + rng.uniform(-0.3, 1.3) * h
    thickness = rng.uniform(8, 38)
    pen = QPen(_c(col, alpha), thickness, Qt.SolidLine,
               Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _draw_corner(p: QPainter, rect: QRectF, rng: random.Random,
                 col: QColor, alpha: int) -> None:
    """Solid wedge radiating from a corner — strong angular fill."""
    w, h = rect.width(), rect.height()
    corner = rng.randint(0, 3)
    cx = rect.x() + (0 if corner in (0, 2) else w)
    cy = rect.y() + (0 if corner in (0, 1) else h)
    r  = rng.uniform(0.45, 1.0) * max(w, h)
    # Filled quarter-circle via arc path
    start_angles = [0, 270, 90, 180]  # TL, TR, BL, BR (Qt degrees, CCW)
    path = QPainterPath()
    path.moveTo(cx, cy)
    path.arcTo(QRectF(cx - r, cy - r, r * 2, r * 2), start_angles[corner], 90)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(_c(col, alpha))
    p.drawPath(path)


def _draw_triangle(p: QPainter, rect: QRectF, rng: random.Random,
                   col: QColor, alpha: int) -> None:
    """Large filled triangle — sharp, dramatic polygon."""
    w, h = rect.width(), rect.height()
    ox, oy = rect.x(), rect.y()
    pts = [
        QPointF(ox + rng.uniform(-0.1, 0.5) * w, oy + rng.uniform(-0.2, 0.4) * h),
        QPointF(ox + rng.uniform(0.3,  1.1) * w, oy + rng.uniform(0.5,  1.2) * h),
        QPointF(ox + rng.uniform(0.5,  1.2) * w, oy + rng.uniform(-0.3, 0.4) * h),
    ]
    path = QPainterPath()
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(_c(col, alpha))
    p.drawPath(path)


def _draw_stripe(p: QPainter, rect: QRectF, rng: random.Random,
                 col: QColor, alpha: int) -> None:
    """Diagonal parallelogram band — stripy, directional."""
    w, h = rect.width(), rect.height()
    ox, oy = rect.x(), rect.y()
    band_w  = rng.uniform(0.1, 0.35) * w
    diag    = rng.uniform(0.3, 0.8) * h * rng.choice([-1, 1])
    x_start = ox + rng.uniform(0.0, 0.6) * w
    path = QPainterPath()
    path.moveTo(x_start + diag,          oy)
    path.lineTo(x_start + band_w + diag, oy)
    path.lineTo(x_start + band_w - diag, oy + h)
    path.lineTo(x_start - diag,          oy + h)
    path.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(_c(col, alpha))
    p.drawPath(path)


def _draw_dots(p: QPainter, rect: QRectF, rng: random.Random,
               col: QColor, alpha: int) -> None:
    """Cluster of 4–8 solid filled circles — scattered, playful."""
    w, h = rect.width(), rect.height()
    cluster_x = rect.x() + rng.uniform(0.1, 0.9) * w
    cluster_y = rect.y() + rng.uniform(0.1, 0.9) * h
    spread    = rng.uniform(0.06, 0.25) * h
    dot_r     = rng.uniform(0.04, 0.12) * h
    n         = rng.randint(4, 8)
    p.setPen(Qt.NoPen)
    p.setBrush(_c(col, alpha))
    for _ in range(n):
        dx = rng.uniform(-spread, spread)
        dy = rng.uniform(-spread, spread)
        p.drawEllipse(QPointF(cluster_x + dx, cluster_y + dy), dot_r, dot_r)


def _draw_ring(p: QPainter, rect: QRectF, rng: random.Random,
               col: QColor, alpha: int) -> None:
    """Hollow ring (donut) — crisp circular outline with weight."""
    w, h = rect.width(), rect.height()
    cx = rect.x() + rng.uniform(0.0, 1.0) * w
    cy = rect.y() + rng.uniform(0.0, 1.0) * h
    outer = rng.uniform(0.3, 0.85) * h
    inner = outer * rng.uniform(0.35, 0.65)
    outer_path = QPainterPath()
    outer_path.addEllipse(QPointF(cx, cy), outer, outer)
    inner_path = QPainterPath()
    inner_path.addEllipse(QPointF(cx, cy), inner, inner)
    ring = outer_path.subtracted(inner_path)
    p.setPen(Qt.NoPen)
    p.setBrush(_c(col, alpha))
    p.drawPath(ring)


_DRAW_FN = {
    "blob":     _draw_blob,
    "rect":     _draw_rect,
    "line":     _draw_line,
    "corner":   _draw_corner,
    "triangle": _draw_triangle,
    "stripe":   _draw_stripe,
    "dots":     _draw_dots,
    "ring":     _draw_ring,
}


# ── Card widget ───────────────────────────────────────────────────────────────

class ReminderCard(QFrame):
    edit_requested   = Signal(object)
    done_requested   = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, reminder: Reminder, parent=None) -> None:
        super().__init__(parent)
        self._reminder = reminder
        self._hovered  = False
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

        if self._reminder.details:
            det = QLabel(self._reminder.details[:120])
            det.setObjectName("CardDetails")
            det.setWordWrap(True)
            outer.addWidget(det)

        trigger_text = self._format_trigger()
        if trigger_text:
            trig = QLabel(trigger_text)
            trig.setObjectName("CardTrigger")
            outer.addWidget(trig)

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

        # White base
        p.fillRect(self.rect(), QColor(255, 255, 255))

        # Composite art
        self._paint_art(p, r)

        # Frosted veil keeps dark text legible over vivid art
        p.fillPath(clip, QColor(255, 255, 255, 75))

        # Border
        p.setClipping(False)
        border_alpha = 210 if self._hovered else 70
        p.setPen(QPen(QColor(255, 107, 53, border_alpha), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, radius, radius)
        p.end()

    def _paint_art(self, p: QPainter, rect: QRectF) -> None:
        seed = (self._reminder.id or abs(hash(self._reminder.name))) & 0x7FFFFFFF
        rng  = random.Random(seed)
        A, B = _SCHEMES[seed % len(_SCHEMES)]

        # ── Base layer (one of three types) ──────────────────────────────────
        base = seed % 3
        if base == 0:
            # Solid tint of primary colour
            p.fillRect(rect, _c(A, 35))
        elif base == 1:
            # Diagonal linear gradient primary → secondary
            g = QLinearGradient(rect.topLeft(), rect.bottomRight())
            if seed % 2:
                g = QLinearGradient(rect.bottomLeft(), rect.topRight())
            g.setColorAt(0.0, _c(A, 55))
            g.setColorAt(1.0, _c(B, 45))
            p.fillRect(rect, QBrush(g))
        # base == 2: pure white (nothing extra)

        # ── Element layers ────────────────────────────────────────────────────
        # Pick 5–8 elements via weighted random; each gets a colour and alpha.
        n = rng.randint(5, 8)
        chosen = rng.choices(_TYPES, weights=_WEIGHTS, k=n)

        for elem in chosen:
            # Alternate between primary and secondary with slight mix
            t    = rng.uniform(0.0, 0.3)
            col  = _mix(A, B, t) if rng.random() < 0.5 else _mix(B, A, t)
            alpha = rng.randint(110, 225)
            _DRAW_FN[elem](p, rect, rng, col, alpha)

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
