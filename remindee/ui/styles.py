from __future__ import annotations

from pathlib import Path
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication, QCalendarWidget

_QSS_PATH = Path(__file__).parent.parent / "resources" / "styles.qss"

# Token order matters: longer/more-specific tokens must come before their prefixes
_THEMES: dict[str, dict[str, str]] = {
    "light": {
        "@dialog_bg":     "rgba(255, 252, 248, 0.97)",
        "@bg_gradient":   "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFF6EF, stop:1 #FFE8D0)",
        "@surface_card":  "rgba(255, 255, 255, 0.52)",   # glass card (was 0.72)
        "@surface_side":  "rgba(255, 255, 255, 0.40)",   # secondary surface
        "@surface2":      "rgba(255, 107, 53, 0.07)",
        "@surface":       "rgba(255, 255, 255, 0.65)",   # form inputs (was 0.80)
        "@border_glass":  "rgba(255, 255, 255, 0.70)",
        "@border":        "rgba(255, 107, 53, 0.20)",
        "@cal_nav":       "rgba(255, 107, 53, 0.08)",
        "@accent_hover":  "#E85D2A",
        "@accent":        "#FF6B35",
        "@text2":         "#8A5030",                     # slightly darker for glass contrast
        "@text":          "#1C0800",
        "@danger":        "#EF4444",
        "@success":       "#22C55E",
        "@shadow":        "rgba(255, 107, 53, 0.12)",
        "@radius":        "14px",
    },
    "dark": {
        "@dialog_bg":     "rgba(22, 14, 8, 0.97)",
        "@bg_gradient":   "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0D0804, stop:1 #1A0E06)",
        "@surface_card":  "rgba(255, 255, 255, 0.10)",   # glass card on dark blur
        "@surface_side":  "rgba(255, 255, 255, 0.07)",
        "@surface2":      "rgba(255, 107, 53, 0.12)",
        "@surface":       "rgba(255, 255, 255, 0.09)",   # form inputs
        "@border_glass":  "rgba(255, 255, 255, 0.14)",
        "@border":        "rgba(255, 107, 53, 0.22)",
        "@cal_nav":       "rgba(255, 107, 53, 0.14)",
        "@accent_hover":  "#FF8050",
        "@accent":        "#FF6B35",
        "@text2":         "rgba(255, 185, 130, 0.70)",
        "@text":          "rgba(255, 245, 232, 0.95)",
        "@danger":        "#FF5C5C",
        "@success":       "#4CAF50",
        "@shadow":        "rgba(0, 0, 0, 0.35)",
        "@radius":        "14px",
    },
}

# Per-theme palette colours for QCalendarWidget cells.
# QSS alone cannot reliably override the internal QAbstractItemView background
# when WA_TranslucentBackground is set on the window — use QPalette instead.
_CAL_PALETTES = {
    "light": {
        "base":            QColor("#FFFCF8"),
        "alt_base":        QColor(255, 242, 230),
        "text":            QColor("#1C0800"),
        "window":          QColor("#FFF6EF"),
        "window_text":     QColor("#1C0800"),
        "button":          QColor("#FFF6EF"),
        "button_text":     QColor("#1C0800"),
        "highlight":       QColor("#FF6B35"),
        "highlighted_text": QColor("#FFFFFF"),
    },
    "dark": {
        "base":            QColor(22, 12, 6),
        "alt_base":        QColor(35, 20, 10),
        "text":            QColor(255, 245, 232),
        "window":          QColor(18, 10, 4),
        "window_text":     QColor(255, 245, 232),
        "button":          QColor(18, 10, 4),
        "button_text":     QColor(255, 245, 232),
        "highlight":       QColor("#FF6B35"),
        "highlighted_text": QColor("#FFFFFF"),
    },
}


def _resolve_theme(theme: str) -> str:
    if theme == "system":
        app = QApplication.instance()
        if app:
            bg = app.palette().color(QPalette.ColorRole.Window)
            return "dark" if bg.lightness() < 128 else "light"
        return "light"
    return theme if theme in _THEMES else "light"


def load_qss(theme: str) -> str:
    resolved = _resolve_theme(theme)
    tokens = _THEMES[resolved]
    try:
        raw = _QSS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    for token, value in tokens.items():
        raw = raw.replace(token, value)
    return raw


def apply_theme(app: QApplication, theme: str) -> None:
    app.setStyleSheet(load_qss(theme))


def apply_calendar_palette(cal: QCalendarWidget, theme: str = "light") -> None:
    """Set QPalette on a QCalendarWidget so cells are never transparent/black."""
    resolved = _resolve_theme(theme)
    c = _CAL_PALETTES[resolved]

    p = cal.palette()
    p.setColor(QPalette.ColorRole.Base,            c["base"])
    p.setColor(QPalette.ColorRole.AlternateBase,   c["alt_base"])
    p.setColor(QPalette.ColorRole.Text,            c["text"])
    p.setColor(QPalette.ColorRole.BrightText,      c["text"])
    p.setColor(QPalette.ColorRole.Window,          c["window"])
    p.setColor(QPalette.ColorRole.WindowText,      c["window_text"])
    p.setColor(QPalette.ColorRole.Button,          c["button"])
    p.setColor(QPalette.ColorRole.ButtonText,      c["button_text"])
    p.setColor(QPalette.ColorRole.Highlight,       c["highlight"])
    p.setColor(QPalette.ColorRole.HighlightedText, c["highlighted_text"])
    cal.setPalette(p)
    # Also force the internal viewport to repaint with the new palette
    cal.setAutoFillBackground(True)
