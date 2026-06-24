from __future__ import annotations

from pathlib import Path
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

_QSS_PATH = Path(__file__).parent.parent / "resources" / "styles.qss"

# Token order matters: longer/more-specific tokens must come before their prefixes
# so @accent_hover is replaced before @accent, etc.
_THEMES: dict[str, dict[str, str]] = {
    "light": {
        "@bg_gradient":   "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFF6EF, stop:1 #FFE8D0)",
        "@surface_card":  "rgba(255, 255, 255, 0.72)",
        "@surface_side":  "rgba(255, 255, 255, 0.60)",
        "@surface2":      "rgba(255, 107, 53, 0.07)",
        "@surface":       "rgba(255, 255, 255, 0.80)",
        "@border_glass":  "rgba(255, 255, 255, 0.90)",
        "@border":        "rgba(255, 107, 53, 0.18)",
        "@cal_nav":       "rgba(255, 107, 53, 0.08)",
        "@cal_alt":       "rgba(255, 107, 53, 0.04)",
        "@cal_bg":        "rgba(255, 252, 248, 0.96)",
        "@accent_hover":  "#E85D2A",
        "@accent":        "#FF6B35",
        "@text2":         "#9A6040",
        "@text":          "#1C0800",
        "@danger":        "#EF4444",
        "@success":       "#22C55E",
        "@shadow":        "rgba(255, 107, 53, 0.10)",
        "@radius":        "14px",
    },
    "dark": {
        "@bg_gradient":   "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0D0804, stop:1 #1A0E06)",
        "@surface_card":  "rgba(255, 255, 255, 0.07)",
        "@surface_side":  "rgba(255, 255, 255, 0.05)",
        "@surface2":      "rgba(255, 107, 53, 0.10)",
        "@surface":       "rgba(255, 255, 255, 0.06)",
        "@border_glass":  "rgba(255, 255, 255, 0.10)",
        "@border":        "rgba(255, 107, 53, 0.18)",
        "@cal_nav":       "rgba(255, 107, 53, 0.12)",
        "@cal_alt":       "rgba(255, 107, 53, 0.06)",
        "@cal_bg":        "rgba(22, 12, 6, 0.96)",
        "@accent_hover":  "#FF8050",
        "@accent":        "#FF6B35",
        "@text2":         "rgba(255, 175, 120, 0.60)",
        "@text":          "rgba(255, 245, 232, 0.95)",
        "@danger":        "#FF5C5C",
        "@success":       "#4CAF50",
        "@shadow":        "rgba(0, 0, 0, 0.30)",
        "@radius":        "14px",
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
