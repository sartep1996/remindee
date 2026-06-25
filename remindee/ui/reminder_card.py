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

# ── Helpers ───────────────────────────────────────────────────────────────────

def _c(col: QColor, alpha: int) -> QColor:
    out = QColor(col)
    out.setAlpha(max(0, min(255, alpha)))
    return out


def _lum(c: QColor) -> int:
    """Perceived luminance 0–255."""
    return (c.red() * 299 + c.green() * 587 + c.blue() * 114) // 1000


# ── 20 rich multi-colour palettes (3–5 QColors each) ─────────────────────────

_SCHEMES: list[tuple[QColor, ...]] = [
    # 0  Neon Electric
    (QColor(138, 43, 226), QColor(  0, 255, 255), QColor(255,   0, 170), QColor(255, 255,  50)),
    # 1  Fire Drama
    (QColor(255, 80,   0), QColor(220,   0,  40), QColor(255, 210,  30), QColor(255, 150,  60)),
    # 2  Cool Futuristic
    (QColor(  0, 200, 180), QColor(  0, 100, 255), QColor(160,   0, 255), QColor(180, 240, 255)),
    # 3  Sunset Aurora
    (QColor(255, 80, 180), QColor(255, 130,   0), QColor(140,   0, 200), QColor(255, 240,  60)),
    # 4  Jewel Tones
    (QColor( 30, 140, 255), QColor(  0, 190,  90), QColor(180,  50, 230), QColor(255, 215,   0)),
    # 5  Candy
    (QColor(255, 105, 180), QColor(180, 120, 255), QColor( 80, 230, 170), QColor(255, 240,  90)),
    # 6  Tropical
    (QColor(255,  75,  60), QColor( 60, 230,  60), QColor(  0, 215, 215), QColor(255, 205,   0)),
    # 7  Midnight Cobalt — on dark bg, vivid blues pop
    (QColor( 40, 120, 255), QColor(  0, 200, 255), QColor(120,  60, 255), QColor(180, 220, 255)),
    # 8  Autumn Harvest — warm vivid oranges
    (QColor(255, 110,  20), QColor(220, 170,   0), QColor(180,  60,  10), QColor(255, 220, 100)),
    # 9  Pastel Dream — intentionally soft
    (QColor(200, 170, 240), QColor(255, 200, 175), QColor(160, 215, 245), QColor(235, 245, 190)),
    # 10 Acid Punk
    (QColor(200, 255,   0), QColor(255,   0, 110), QColor(  0, 255, 130), QColor(200,   0, 255)),
    # 11 Copper & Teal
    (QColor(220, 140,  50), QColor(  0, 175, 155), QColor(255, 190,  60), QColor( 20, 130, 115)),
    # 12 Rose Gold
    (QColor(255, 160, 150), QColor(230, 120,  90), QColor(255, 210, 190), QColor(200,  90, 100)),
    # 13 Cyberpunk Night — vivid neon on dark
    (QColor(255,  10, 200), QColor(  0, 240, 200), QColor(255, 230,   0), QColor(150,   0, 255)),
    # 14 Forest Mist
    (QColor( 60, 185,  60), QColor(130, 210,  90), QColor(  0, 140,  80), QColor(200, 240, 160)),
    # 15 Ocean Depth
    (QColor(  0, 155, 200), QColor( 60, 200, 220), QColor(  0,  80, 150), QColor(180, 235, 255)),
    # 16 Berry Blast
    (QColor(220,  40, 140), QColor(255, 100, 170), QColor(150,  20, 100), QColor(255, 185, 215)),
    # 17 Solar Flare
    (QColor(255, 210,   0), QColor(255, 120,   0), QColor(230,   0,  50), QColor(255, 250, 150)),
    # 18 Arctic Ice
    (QColor( 80, 190, 240), QColor(160, 225, 255), QColor( 20, 130, 210), QColor(220, 248, 255)),
    # 19 Ink & Gold
    (QColor(200, 160,  20), QColor(255, 215,  55), QColor(140, 100,  10), QColor(255, 240, 120)),
]

_SCHEME_NAMES = [
    "Neon Electric", "Fire Drama", "Cool Futuristic", "Sunset Aurora",
    "Jewel Tones", "Candy", "Tropical", "Midnight Cobalt",
    "Autumn Harvest", "Pastel Dream", "Acid Punk", "Copper & Teal",
    "Rose Gold", "Cyberpunk Night", "Forest Mist", "Ocean Depth",
    "Berry Blast", "Solar Flare", "Arctic Ice", "Ink & Gold",
]

# Very-dark tinted bases for dark cards, one per palette
_DARK_BASES: list[QColor] = [
    QColor( 12,  3, 28),  # 0  Neon Electric
    QColor( 24,  4,  2),  # 1  Fire Drama
    QColor(  0, 12, 25),  # 2  Cool Futuristic
    QColor( 22,  5, 14),  # 3  Sunset Aurora
    QColor(  2,  8, 28),  # 4  Jewel Tones
    QColor( 28,  8, 22),  # 5  Candy
    QColor( 20,  8,  4),  # 6  Tropical
    QColor(  3,  6, 28),  # 7  Midnight Cobalt
    QColor( 22,  8,  0),  # 8  Autumn Harvest
    QColor( 18, 16, 26),  # 9  Pastel Dream
    QColor(  8, 22,  0),  # 10 Acid Punk
    QColor(  6, 20, 17),  # 11 Copper & Teal
    QColor( 24,  8, 10),  # 12 Rose Gold
    QColor(  8,  0, 20),  # 13 Cyberpunk Night
    QColor(  2, 16,  2),  # 14 Forest Mist
    QColor(  0,  8, 20),  # 15 Ocean Depth
    QColor( 20,  0, 14),  # 16 Berry Blast
    QColor( 24, 12,  0),  # 17 Solar Flare
    QColor(  8, 16, 26),  # 18 Arctic Ice
    QColor( 12, 10,  2),  # 19 Ink & Gold
]

_STYLE_NAMES = [
    "mega_blob", "parallel_lines", "big_rect", "corner_wedge",
    "triangle", "diagonal_split", "dot_field", "ring",
]


# ── Base-layer & grain helpers ────────────────────────────────────────────────

def _draw_base(p: QPainter, rect: QRectF, rng: random.Random,
               palette: tuple[QColor, ...], seed: int) -> None:
    """Multi-stop gradient base for light cards — luminance-aware alpha."""
    A, B, *rest = palette
    C = rest[0] if rest else A

    # Pick the brightest colour from the first 3 for the lead stop,
    # so dark-hued palettes (Midnight Cobalt, Ink & Gold) still look vivid.
    lead = max((A, B, C), key=_lum)
    mid  = B if lead is not B else A
    tail = C if lead is not C else A

    # Scale alpha by luminance so darker lead colours stay subtle.
    lum  = _lum(lead)
    a0   = max(80,  min(170, lum))
    a1   = max(55,  min(120, lum // 2 + 40))
    a2   = max(50,  min(140, lum))

    cx, cy = rect.center().x(), rect.center().y()
    w,  h  = rect.width(), rect.height()
    mode   = seed % 4

    if mode == 0:
        g = QLinearGradient(rect.left(), cy, rect.right(), cy)
        g.setColorAt(0.0, _c(lead, a0))
        g.setColorAt(0.45, _c(mid, a1))
        g.setColorAt(1.0, _c(tail, a2))
        p.fillRect(rect, g)
    elif mode == 1:
        g = QLinearGradient(rect.topLeft(), rect.bottomRight())
        g.setColorAt(0.0, _c(lead, a0))
        g.setColorAt(0.5, _c(mid, a1))
        g.setColorAt(1.0, _c(tail, a2))
        p.fillRect(rect, g)
    elif mode == 2:
        g = QRadialGradient(cx, cy, max(w, h) * 0.65)
        g.setColorAt(0.0, _c(lead, a0))
        g.setColorAt(0.5, _c(mid, a1))
        g.setColorAt(1.0, _c(tail, 40))
        p.fillRect(rect, g)
    else:
        g = QLinearGradient(cx, rect.top(), cx, rect.bottom())
        g.setColorAt(0.0, _c(mid, a1))
        g.setColorAt(0.5, _c(lead, a0))
        g.setColorAt(1.0, _c(tail, a2))
        p.fillRect(rect, g)


def _draw_grain(p: QPainter, rect: QRectF, rng: random.Random) -> None:
    """250–380 random 1×1 px dots to simulate film grain."""
    x0, y0 = int(rect.left()), int(rect.top())
    w,  h  = int(rect.width()), int(rect.height())
    p.save()
    for _ in range(rng.randint(250, 380)):
        lum = rng.randint(80, 240)
        p.fillRect(
            x0 + rng.randint(0, w - 1),
            y0 + rng.randint(0, h - 1),
            1, 1,
            QColor(lum, lum, lum, rng.randint(12, 25)),
        )
    p.restore()


# ── 8 primary style functions ─────────────────────────────────────────────────

def _style_mega_blob(p: QPainter, rect: QRectF, rng: random.Random,
                     palette: tuple[QColor, ...]) -> None:
    """Large 5-stop radial blob (off-centre) + two accent blobs."""
    A, B, *rest = palette
    C = rest[0] if rest else A
    D = rest[1] if len(rest) > 1 else B
    w, h = rect.width(), rect.height()

    # Primary blob — offset toward a random edge
    side = rng.randint(0, 3)
    cx = (rect.x() + rng.uniform(0.0, 0.3) * w  if side == 0 else
          rect.x() + rng.uniform(0.7, 1.0) * w  if side == 1 else
          rect.x() + rng.uniform(0.3, 0.7) * w)
    cy = (rect.y() + rng.uniform(0.3, 0.7) * h  if side < 2 else
          rect.y() + rng.uniform(0.0, 0.3) * h  if side == 2 else
          rect.y() + rng.uniform(0.7, 1.0) * h)
    r  = rng.uniform(0.7, 1.1) * max(w, h)

    g = QRadialGradient(QPointF(cx, cy), r)
    g.setColorAt(0.00, _c(A, 240))
    g.setColorAt(0.25, _c(B, 200))
    g.setColorAt(0.50, _c(C, 150))
    g.setColorAt(0.75, _c(D, 85))
    g.setColorAt(1.00, _c(A, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), r, r)

    # Accent blob — contrasting colour, top-right area
    cx2 = rect.x() + rng.uniform(0.5, 0.95) * w
    cy2 = rect.y() + rng.uniform(0.0,  0.45) * h
    r2  = rng.uniform(0.2, 0.45) * h
    g2  = QRadialGradient(QPointF(cx2, cy2), r2)
    g2.setColorAt(0.0, _c(C, 200))
    g2.setColorAt(1.0, _c(C, 0))
    p.setBrush(QBrush(g2))
    p.drawEllipse(QPointF(cx2, cy2), r2, r2)

    # Small highlight blob — bottom-left
    cx3 = rect.x() + rng.uniform(0.0, 0.4) * w
    cy3 = rect.y() + rng.uniform(0.55, 1.0) * h
    r3  = rng.uniform(0.1, 0.28) * h
    g3  = QRadialGradient(QPointF(cx3, cy3), r3)
    g3.setColorAt(0.0, _c(D, 180))
    g3.setColorAt(1.0, _c(D, 0))
    p.setBrush(QBrush(g3))
    p.drawEllipse(QPointF(cx3, cy3), r3, r3)


def _style_parallel_lines(p: QPainter, rect: QRectF, rng: random.Random,
                           palette: tuple[QColor, ...]) -> None:
    """5–9 thick diagonal lines spanning the full card — racing stripes."""
    A, B, *rest = palette
    C = rest[0] if rest else A
    D = rest[1] if len(rest) > 1 else B
    colors = [A, B, C, D]

    n     = rng.randint(5, 9)
    thick = rng.uniform(12, 28)
    slope = rng.uniform(-0.6, 0.6)   # dy/dx — gives diagonal slant

    p.save()
    p.setBrush(Qt.NoBrush)
    for i in range(n):
        t   = (i + 0.5) / n
        y0  = rect.top() + t * rect.height()
        col = colors[i % len(colors)]
        pen = QPen(_c(col, rng.randint(175, 235)), thick, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(
            QPointF(rect.left()  - rect.width() * 0.05, y0),
            QPointF(rect.right() + rect.width() * 0.05, y0 + slope * rect.width()),
        )
    p.restore()


def _style_big_rect(p: QPainter, rect: QRectF, rng: random.Random,
                    palette: tuple[QColor, ...]) -> None:
    """3 nested rectangles in gradient fill — bold concentric geometry."""
    A, B, *rest = palette
    C = rest[0] if rest else A
    D = rest[1] if len(rest) > 1 else B
    w, h = rect.width(), rect.height()

    p.save()
    # Outer fill
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0.0, _c(A, 170))
    g.setColorAt(1.0, _c(B, 130))
    p.fillRect(rect, g)

    # Inset rect
    m1     = rng.uniform(0.06, 0.16)
    inner1 = rect.adjusted(w * m1, h * m1, -w * m1, -h * m1)
    g2     = QLinearGradient(inner1.topLeft(), inner1.bottomRight())
    g2.setColorAt(0.0, _c(C, 190))
    g2.setColorAt(1.0, _c(D, 110))
    p.fillRect(inner1, g2)

    # Small centred accent rect
    m2     = rng.uniform(0.28, 0.42)
    inner2 = rect.adjusted(w * m2, h * m2, -w * m2, -h * m2)
    p.fillRect(inner2, _c(A, 200))
    p.restore()


def _style_corner_wedge(p: QPainter, rect: QRectF, rng: random.Random,
                         palette: tuple[QColor, ...]) -> None:
    """Gradient wedge from a corner + diagonal accent stripe + dot highlight."""
    A, B, *rest = palette
    C = rest[0] if rest else A
    D = rest[1] if len(rest) > 1 else B
    w, h = rect.width(), rect.height()

    corner = rng.choice(["tl", "tr", "bl", "br"])
    p.save()
    p.setPen(Qt.NoPen)

    path = QPainterPath()
    if corner == "tl":
        path.moveTo(rect.topLeft())
        path.lineTo(rect.left() + w * rng.uniform(0.5, 0.95), rect.top())
        path.lineTo(rect.left(), rect.top() + h * rng.uniform(0.5, 0.95))
    elif corner == "tr":
        path.moveTo(rect.topRight())
        path.lineTo(rect.right() - w * rng.uniform(0.5, 0.95), rect.top())
        path.lineTo(rect.right(), rect.top() + h * rng.uniform(0.5, 0.95))
    elif corner == "bl":
        path.moveTo(rect.bottomLeft())
        path.lineTo(rect.left() + w * rng.uniform(0.5, 0.95), rect.bottom())
        path.lineTo(rect.left(), rect.bottom() - h * rng.uniform(0.5, 0.95))
    else:
        path.moveTo(rect.bottomRight())
        path.lineTo(rect.right() - w * rng.uniform(0.5, 0.95), rect.bottom())
        path.lineTo(rect.right(), rect.bottom() - h * rng.uniform(0.5, 0.95))
    path.closeSubpath()

    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0.0, _c(A, 225))
    g.setColorAt(0.5, _c(B, 185))
    g.setColorAt(1.0, _c(C, 125))
    p.fillPath(path, QBrush(g))

    # Diagonal accent stripe
    sy = rect.top() + h * rng.uniform(0.5, 0.8)
    sh = h * rng.uniform(0.04, 0.10)
    p.fillRect(QRectF(rect.left(), sy, w, sh), _c(D, 140))

    # Soft highlight dot
    dr  = min(w, h) * rng.uniform(0.05, 0.11)
    dx  = rect.left() + w * rng.uniform(0.2, 0.8)
    dy  = rect.top()  + h * rng.uniform(0.2, 0.8)
    gd  = QRadialGradient(dx, dy, dr)
    gd.setColorAt(0.0, _c(C, 200))
    gd.setColorAt(1.0, _c(C, 0))
    p.setBrush(QBrush(gd))
    p.drawEllipse(QPointF(dx, dy), dr, dr)
    p.restore()


def _style_triangle(p: QPainter, rect: QRectF, rng: random.Random,
                    palette: tuple[QColor, ...]) -> None:
    """Structured edge-anchored triangles — fan from one point to opposite edge."""
    A, B, *rest = palette
    C = rest[0] if rest else A
    D = rest[1] if len(rest) > 1 else B
    colors = [A, B, C, D]
    w, h = rect.width(), rect.height()
    ox, oy = rect.x(), rect.y()

    # Fan origin — one of 4 corners or mid-edges
    variants = [
        (ox, oy),               # TL corner
        (ox + w, oy),           # TR corner
        (ox, oy + h),           # BL corner
        (ox + w, oy + h),       # BR corner
        (ox + w * 0.5, oy),     # top centre
        (ox + w * 0.5, oy + h), # bottom centre
    ]
    fx, fy = rng.choice(variants)

    n_fan  = rng.randint(3, 6)
    # Divide the opposite edge into n_fan segments
    p.save()
    p.setPen(Qt.NoPen)
    for i in range(n_fan):
        col   = colors[i % len(colors)]
        alpha = rng.randint(140, 220)
        t1    = i / n_fan
        t2    = (i + 1) / n_fan
        # Points along opposite edge
        if fx == ox or fx == ox + w:
            # Origin is left or right — fan toward opposite vertical edge
            ex = ox + w if fx < ox + w * 0.5 else ox
            y1 = oy + t1 * h
            y2 = oy + t2 * h
            pts = [QPointF(fx, fy), QPointF(ex, y1), QPointF(ex, y2)]
        else:
            # Origin is top or bottom centre — fan toward opposite horizontal edge
            ey = oy + h if fy < oy + h * 0.5 else oy
            x1 = ox + t1 * w
            x2 = ox + t2 * w
            pts = [QPointF(fx, fy), QPointF(x1, ey), QPointF(x2, ey)]
        path = QPainterPath()
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
        p.fillPath(path, _c(col, alpha))
    p.restore()


def _style_diagonal_split(p: QPainter, rect: QRectF, rng: random.Random,
                           palette: tuple[QColor, ...]) -> None:
    """Card split into 3 diagonal zones: A (left) + C (accent stripe) + B (right)."""
    A, B, *rest = palette
    C = rest[0] if rest else A
    w = rect.width()

    t_x = rect.left() + w * rng.uniform(0.25, 0.65)
    b_x = rect.left() + w * rng.uniform(0.25, 0.65)
    sw  = w * rng.uniform(0.04, 0.13)

    p.save()
    p.setPen(Qt.NoPen)

    # Left zone — A
    pa = QPainterPath()
    pa.moveTo(rect.topLeft())
    pa.lineTo(t_x, rect.top())
    pa.lineTo(b_x, rect.bottom())
    pa.lineTo(rect.bottomLeft())
    pa.closeSubpath()
    ga = QLinearGradient(rect.left(), rect.top(), t_x, rect.bottom())
    ga.setColorAt(0.0, _c(A, 225))
    ga.setColorAt(1.0, _c(A, 155))
    p.fillPath(pa, QBrush(ga))

    # Right zone — B
    pb = QPainterPath()
    pb.moveTo(t_x + sw, rect.top())
    pb.lineTo(rect.topRight())
    pb.lineTo(rect.bottomRight())
    pb.lineTo(b_x + sw, rect.bottom())
    pb.closeSubpath()
    gb = QLinearGradient(t_x + sw, rect.top(), rect.right(), rect.bottom())
    gb.setColorAt(0.0, _c(B, 185))
    gb.setColorAt(1.0, _c(B, 225))
    p.fillPath(pb, QBrush(gb))

    # Accent stripe — C
    pc = QPainterPath()
    pc.moveTo(t_x, rect.top())
    pc.lineTo(t_x + sw, rect.top())
    pc.lineTo(b_x + sw, rect.bottom())
    pc.lineTo(b_x, rect.bottom())
    pc.closeSubpath()
    gc = QLinearGradient(t_x, rect.top(), b_x + sw, rect.bottom())
    gc.setColorAt(0.0, _c(C, 245))
    gc.setColorAt(1.0, _c(C, 165))
    p.fillPath(pc, QBrush(gc))
    p.restore()


def _style_dot_field(p: QPainter, rect: QRectF, rng: random.Random,
                     palette: tuple[QColor, ...]) -> None:
    """Grid of radial-gradient circles cycling palette colours."""
    A, B, *rest = palette
    C = rest[0] if rest else A
    D = rest[1] if len(rest) > 1 else B
    colors = [A, B, C, D]

    cols = rng.randint(6, 10)
    rows = rng.randint(4, 7)
    dx   = rect.width() / cols
    dy   = rect.height() / rows

    p.save()
    p.setPen(Qt.NoPen)
    idx = 0
    for row in range(rows):
        for col in range(cols):
            col_color = colors[idx % len(colors)]
            idx += 1
            alpha = rng.randint(110, 220)
            r     = min(dx, dy) * rng.uniform(0.18, 0.44)
            cx    = rect.left() + (col + 0.5) * dx + rng.uniform(-dx * 0.15, dx * 0.15)
            cy    = rect.top()  + (row + 0.5) * dy + rng.uniform(-dy * 0.15, dy * 0.15)
            g     = QRadialGradient(cx, cy, r)
            g.setColorAt(0.0, _c(col_color, alpha))
            g.setColorAt(1.0, _c(col_color, 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(cx, cy), r, r)
    p.restore()


def _style_ring(p: QPainter, rect: QRectF, rng: random.Random,
                palette: tuple[QColor, ...]) -> None:
    """Concentric colour rings drawn outside-in with correct shrinking radius."""
    A, B, *rest = palette
    C = rest[0] if rest else A
    D = rest[1] if len(rest) > 1 else B
    colors = [A, B, C, D]

    cx     = rect.left() + rect.width()  * rng.uniform(0.3, 0.7)
    cy     = rect.top()  + rect.height() * rng.uniform(0.3, 0.7)
    n      = rng.randint(4, 7)
    max_r  = max(rect.width(), rect.height()) * rng.uniform(0.55, 0.85)
    band   = max_r / n         # radial width of each ring
    gap    = band * 0.3        # gap between rings

    p.save()
    p.setPen(Qt.NoPen)
    for i in range(n):
        outer = max_r - i * band
        inner = max(0.0, outer - (band - gap))
        if outer <= 0:
            break
        col   = colors[i % len(colors)]
        alpha = rng.randint(90, 200)
        ring_path = QPainterPath()
        ring_path.addEllipse(QPointF(cx, cy), outer, outer)
        hole_path = QPainterPath()
        hole_path.addEllipse(QPointF(cx, cy), inner, inner)
        ring = ring_path.subtracted(hole_path)
        p.setBrush(_c(col, alpha))
        p.drawPath(ring)
    p.restore()


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


# ── Dark-card text overrides ──────────────────────────────────────────────────

_DARK_TEXT    = "color: rgba(238, 222, 205, 0.97);"
_DARK_TEXT2   = "color: rgba(190, 165, 140, 0.90);"
_DARK_BADGE   = (
    "background: rgba(255,255,255,0.12); color: rgba(230,215,195,0.92);"
    "border: 1px solid rgba(255,255,255,0.18); border-radius: 6px;"
    "padding: 2px 9px; font-size: 10px; font-weight: 700;"
)
_DARK_BTN = (
    "QPushButton { background: transparent; border: none; border-radius: 6px;"
    " color: rgba(225, 205, 185, 0.88); font-size: 19px; padding: 4px 6px; }"
    "QPushButton:hover { background: rgba(255,255,255,0.15); color: white; }"
)


# ── Card widget ───────────────────────────────────────────────────────────────

class ReminderCard(QFrame):
    edit_requested   = Signal(object)
    done_requested   = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, reminder: Reminder, parent=None) -> None:
        super().__init__(parent)
        self._reminder = reminder
        self._hovered  = False

        # Deterministic 31-bit seed — same reminder always gets same art
        self._seed    = (reminder.id or abs(hash(reminder.name))) & 0x7FFFFFFF
        self._is_dark = (self._seed * 11 + 5) % 5 == 0   # ~20 % dark cards

        self.setObjectName("ReminderCard")
        self.setFrameShape(QFrame.Shape.NoFrame)        # no platform border
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

        done_btn = QPushButton("✓")
        done_btn.setObjectName("CardActionBtn")
        done_btn.setFixedSize(38, 38)
        done_btn.setToolTip("Mark Done")
        done_btn.clicked.connect(lambda: self.done_requested.emit(self._reminder))
        top_row.addWidget(done_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("CardActionBtn")
        del_btn.setFixedSize(38, 38)
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
            title.setStyleSheet(_DARK_TEXT)
            freq_badge.setStyleSheet(_DARK_BADGE)
            for btn in (done_btn, del_btn):
                btn.setStyleSheet(_DARK_BTN)
            if det  is not None: det.setStyleSheet(_DARK_TEXT2)
            if trig is not None: trig.setStyleSheet(_DARK_TEXT2)

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

    # ── Painting ─────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r      = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = 14.0

        # Clip all drawing to the rounded card shape
        clip = QPainterPath()
        clip.addRoundedRect(r, radius, radius)
        p.setClipPath(clip)

        # 1. Base fill
        if self._is_dark:
            p.fillRect(self.rect(), _DARK_BASES[self._seed % len(_DARK_BASES)])
        else:
            p.fillRect(self.rect(), QColor(255, 255, 255))

        # 2. Art layer
        self._paint_art(p, r)

        # 3. Frosted veil — ensures text stays readable over vivid art
        veil = QColor(0, 0, 0, 55) if self._is_dark else QColor(255, 255, 255, 72)
        p.fillPath(clip, veil)

        # 4. Border
        p.setClipping(False)
        border_alpha = 220 if self._hovered else (110 if self._is_dark else 70)
        border_col   = (QColor(255, 145, 90, border_alpha) if self._is_dark
                        else QColor(255, 107, 53, border_alpha))
        p.setPen(QPen(border_col, 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, radius, radius)
        # QPainter auto-ends when it goes out of scope — do NOT call p.end() here

    def _paint_art(self, p: QPainter, rect: QRectF) -> None:
        rng     = random.Random(self._seed)
        palette = _SCHEMES[self._seed % len(_SCHEMES)]
        style   = (self._seed * 17 + 5) % len(_STYLES)

        # Multi-stop gradient base layer (light cards only)
        if not self._is_dark:
            _draw_base(p, rect, rng, palette, self._seed)

        # Primary dominant style
        _STYLES[style](p, rect, rng, palette)

        # Film grain on ~40 % of cards
        if (self._seed * 3 + 1) % 5 < 2:
            _draw_grain(p, rect, rng)

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
        self.update()
