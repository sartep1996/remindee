from __future__ import annotations

from pathlib import Path
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

_QSS_PATH = Path(__file__).parent.parent / "resources" / "styles.qss"

_THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "@bg": "#1a1a2e",
        "@surface": "#16213e",
        "@surface2": "#0f3460",
        "@border": "#2d3561",
        "@text": "#e0e0e0",
        "@text2": "#8892a4",
        "@accent": "#5b8cff",
        "@accent_hover": "#4a7aee",
        "@danger": "#ff5c5c",
        "@success": "#4caf50",
        "@radius": "10px",
    },
    "light": {
        "@bg": "#f5f6fa",
        "@surface": "#ffffff",
        "@surface2": "#f0f2f8",
        "@border": "#e1e4ed",
        "@text": "#1a1a2e",
        "@text2": "#6b7280",
        "@accent": "#5b8cff",
        "@accent_hover": "#4a7aee",
        "@danger": "#ef4444",
        "@success": "#22c55e",
        "@radius": "10px",
    },
}


def _resolve_theme(theme: str) -> str:
    if theme == "system":
        app = QApplication.instance()
        if app:
            palette = app.palette()
            bg = palette.color(QPalette.ColorRole.Window)
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
    qss = load_qss(theme)
    app.setStyleSheet(qss)
