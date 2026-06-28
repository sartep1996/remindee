from __future__ import annotations

import math
import random

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QApplication,
)

from remindee.ui.reminder_card import _draw_grain


class QuickNoteDialog(QDialog):
    """Always-on-top floating note-capture window.

    Appears near the cursor when the global REM<space><space> sequence fires.
    Drag anywhere on the background to reposition.
    """

    save_requested     = Signal(str)   # quick-save: creates a reminder immediately
    reminder_requested = Signal(str)   # open full ReminderDialog pre-filled

    _W, _H  = 400, 230
    _RADIUS = 18

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("QuickNoteDialog")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool   # no Dock entry, floats above other apps
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFixedSize(self._W, self._H)

        self._seed     = random.randint(0, 0x7FFF_FFFF)
        self._tick     = 0
        self._drag_pos = None

        self._build()
        self._position_near_cursor()

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick_anim)
        self._anim.start(50)   # 20 fps breathing

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)

        icon_lbl = QLabel("⚡")
        icon_lbl.setStyleSheet("color: white; font-size: 18px;")
        header.addWidget(icon_lbl)

        title_lbl = QLabel("Quick Note")
        title_lbl.setStyleSheet(
            "color: white; font-size: 15px; font-weight: 800; letter-spacing: 0.3px;"
        )
        header.addWidget(title_lbl, stretch=1)

        hint_lbl = QLabel("Ctrl+↵ to save")
        hint_lbl.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 11px;")
        header.addWidget(hint_lbl)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.22); color: white;"
            " border: none; border-radius: 13px; font-size: 11px; font-weight: 700; }"
            "QPushButton:hover { background: rgba(255,255,255,0.40); }"
        )
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)

        root.addLayout(header)

        # Note textarea
        self._note = QTextEdit()
        self._note.setPlaceholderText("What's on your mind?")
        self._note.setStyleSheet(
            "QTextEdit {"
            "  background: rgba(255,255,255,0.88);"
            "  border: 2px solid rgba(255,255,255,0.55);"
            "  border-radius: 12px; color: #1C0800;"
            "  font-size: 14px; padding: 9px 12px;"
            "  selection-background-color: #FF6B35;"
            "}"
            "QTextEdit:focus {"
            "  background: rgba(255,255,255,0.96); border-color: white;"
            "}"
        )
        root.addWidget(self._note, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        remind_btn = QPushButton("Set Reminder…")
        remind_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remind_btn.setStyleSheet(
            "QPushButton {"
            "  background: rgba(255,255,255,0.22); color: white;"
            "  border: 1.5px solid rgba(255,255,255,0.45); border-radius: 9px;"
            "  font-size: 12px; font-weight: 600; padding: 6px 12px;"
            "}"
            "QPushButton:hover { background: rgba(255,255,255,0.36); }"
        )
        remind_btn.clicked.connect(self._on_set_reminder)
        btn_row.addWidget(remind_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            "QPushButton {"
            "  background: rgba(0,0,0,0.14); color: rgba(255,255,255,0.80);"
            "  border: none; border-radius: 9px; font-size: 12px; padding: 6px 14px;"
            "}"
            "QPushButton:hover { background: rgba(0,0,0,0.26); }"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setDefault(False)
        save_btn.setAutoDefault(False)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(
            "QPushButton {"
            "  background: white; color: #E84515;"
            "  border: none; border-radius: 9px;"
            "  font-size: 13px; font-weight: 700; padding: 6px 22px;"
            "}"
            "QPushButton:hover { background: rgba(255,255,255,0.88); }"
            "QPushButton:pressed { background: rgba(255,255,255,0.72); }"
        )
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        root.addLayout(btn_row)

    # ── Positioning ──────────────────────────────────────────────────────────

    def _position_near_cursor(self) -> None:
        from PySide6.QtGui import QCursor
        cursor = QCursor.pos()
        screen = QApplication.screenAt(cursor) or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        x = min(cursor.x() + 24, avail.right()  - self._W - 12)
        y = min(cursor.y() + 24, avail.bottom() - self._H - 12)
        self.move(max(x, avail.left() + 12), max(y, avail.top() + 12))

    # ── Animation ────────────────────────────────────────────────────────────

    def _tick_anim(self) -> None:
        self._tick += 1
        self.update()

    # ── Qt events ────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        # Small delay lets the native activation complete before forcing focus
        QTimer.singleShot(120, self._focus_note)

    def _focus_note(self) -> None:
        self.raise_()
        self.activateWindow()
        self._note.setFocus(Qt.FocusReason.OtherFocusReason)

    def closeEvent(self, event) -> None:
        self._anim.stop()
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:
        key  = event.key()
        mods = event.modifiers()
        if key == Qt.Key.Key_Escape:
            self.reject()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and \
                mods & Qt.KeyboardModifier.ControlModifier:
            self._on_save()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        text = self._note.toPlainText().strip()
        if not text:
            self.reject()
            return
        self.save_requested.emit(text)
        self.accept()

    def _on_set_reminder(self) -> None:
        self.reminder_requested.emit(self._note.toPlainText().strip())
        self.accept()

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r    = float(self._RADIUS)

        # Rounded clip
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), r, r)
        p.setClipPath(clip)

        # Warm orange gradient — write RGBA directly for macOS compositor
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        grad = QLinearGradient(QPointF(0, 0), QPointF(w, h))
        grad.setColorAt(0.0,  QColor(255, 152, 78))
        grad.setColorAt(0.45, QColor(255, 108, 42))
        grad.setColorAt(1.0,  QColor(218, 70, 18))
        p.fillRect(0, 0, w, h, grad)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # Grain (new Random from fixed seed → static texture every frame)
        rng = random.Random(self._seed)
        _draw_grain(p, QRectF(0, 0, w, h), rng)

        # Breathing highlight
        veil_a = int(10 + 8 * math.sin(self._tick * 0.09))
        p.fillRect(0, 0, w, h, QColor(255, 255, 255, veil_a))

        # Inner glass border
        border = QPainterPath()
        border.addRoundedRect(QRectF(1, 1, w - 2, h - 2), r - 1, r - 1)
        p.setPen(QPen(QColor(255, 255, 255, 105), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(border)

        p.end()
