from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRectF,
)
from PySide6.QtGui import (
    QBrush, QColor, QConicalGradient, QPainter, QPainterPath, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel,
    QPushButton, QSystemTrayIcon, QVBoxLayout,
)

from remindee.models.reminder import Reminder
from remindee.utils.database import get_session
from remindee.ui.reminder_card import _SCHEMES, _DARK_BASES, _c

if TYPE_CHECKING:
    from remindee.services.scheduler_service import SchedulerService


class NotificationService:
    def __init__(
        self,
        tray_icon: QSystemTrayIcon,
        scheduler_service: "SchedulerService",
    ) -> None:
        self._tray      = tray_icon
        self._scheduler = scheduler_service
        self._active_bubbles: dict[int, "ActionBubble"] = {}

    def notify(self, reminder: Reminder) -> None:
        msg = reminder.name
        if reminder.details:
            msg += f"\n{reminder.details[:100]}"
        if self._tray.isSystemTrayAvailable():
            self._tray.showMessage(
                "REMINDEE", msg,
                QSystemTrayIcon.MessageIcon.Information, 4000,
            )
        self.show_action_bubble(reminder)

    def show_action_bubble(self, reminder: Reminder) -> None:
        if reminder.id in self._active_bubbles:
            existing = self._active_bubbles[reminder.id]
            try:
                still_visible = existing.isVisible()
            except RuntimeError:
                still_visible = False
                self._active_bubbles.pop(reminder.id, None)
            if still_visible:
                existing.raise_()
                existing.activateWindow()
                return
        bubble = ActionBubble(reminder, self._scheduler, self._on_bubble_closed)
        self._active_bubbles[reminder.id] = bubble
        bubble.show()

    def _on_bubble_closed(self, reminder_id: int) -> None:
        self._active_bubbles.pop(reminder_id, None)


# ── Animated notification bubble ──────────────────────────────────────────────

_BORDER_W = 4      # animated gradient border thickness (px)
_RADIUS   = 22.0   # corner radius of the visible bubble


class ActionBubble(QDialog):
    def __init__(
        self,
        reminder: Reminder,
        scheduler: "SchedulerService",
        on_close_cb,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)

        self._reminder_id = reminder.id
        self._scheduler   = scheduler
        self._on_close_cb = on_close_cb

        # Deterministic art tied to this reminder (same system as cards)
        seed = (reminder.id or abs(hash(reminder.name))) & 0x7FFFFFFF
        self._seed    = seed
        self._palette = _SCHEMES[seed % len(_SCHEMES)]
        self._is_dark = (seed * 11 + 5) % 5 == 0

        # Animation state
        self._phase = 0.0   # conical gradient start-angle, degrees
        self._pulse = 0.0   # sin-based inner glow phase, radians

        self.setObjectName("ActionBubble")
        self.setFixedWidth(430)

        self._build(reminder)

        # Position: bottom-right corner of primary screen
        screen   = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self._final_pos = QPoint(
            screen.right()  - self.width()  - 24,
            screen.bottom() - self.height() - 24,
        )

        # Start below screen so slide-in is visible
        self.move(self._final_pos.x(), screen.bottom() + 10)

        # Slide-in via QPropertyAnimation on pos
        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(480)
        self._slide.setStartValue(QPoint(self._final_pos.x(), screen.bottom() + 10))
        self._slide.setEndValue(self._final_pos)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.start()

        # 50 fps animation ticker
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(20)

        # Auto-dismiss after 30 s
        QTimer.singleShot(30_000, self.close)

    # ── Build layout ─────────────────────────────────────────────────────────

    def _build(self, reminder: Reminder) -> None:
        PAD = _BORDER_W + 16

        root = QVBoxLayout(self)
        root.setContentsMargins(PAD + 2, PAD, PAD + 2, PAD)
        root.setSpacing(12)

        # Header: icon label + title in one row
        header = QHBoxLayout()
        header.setSpacing(10)

        bell = QLabel("🔔")
        bell.setFixedWidth(28)
        bell.setStyleSheet("font-size: 20px;")
        header.addWidget(bell)

        name_lbl = QLabel(reminder.name)
        name_lbl.setWordWrap(True)
        if self._is_dark:
            name_lbl.setStyleSheet(
                "color: rgba(238,222,205,0.97); font-size: 17px; font-weight: 750;"
            )
        else:
            name_lbl.setStyleSheet(
                "color: #1C0800; font-size: 17px; font-weight: 750;"
            )
        header.addWidget(name_lbl, stretch=1)
        root.addLayout(header)

        # Optional details
        if reminder.details:
            det = QLabel(reminder.details[:220])
            det.setWordWrap(True)
            det.setStyleSheet(
                "color: rgba(190,165,140,0.92); font-size: 13px;"
                if self._is_dark
                else "color: #8A5030; font-size: 13px;"
            )
            root.addWidget(det)

        # Separator line — uses a thin QLabel with background
        sep = QLabel()
        sep.setFixedHeight(1)
        A = self._palette[0]
        sep.setStyleSheet(
            f"background: rgba({A.red()},{A.green()},{A.blue()},90);"
        )
        root.addWidget(sep)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        done_btn = QPushButton("✓  Done")
        done_btn.setObjectName("BubbleDoneBtn")
        done_btn.setMinimumHeight(42)
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.clicked.connect(self._mark_done)

        snooze_btn = QPushButton("⏱  Snooze 30m")
        snooze_btn.setObjectName("BubbleSnoozeBtn")
        snooze_btn.setMinimumHeight(42)
        snooze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        snooze_btn.clicked.connect(self._snooze)

        dismiss_btn = QPushButton("✕")
        dismiss_btn.setObjectName("BubbleDismissBtn")
        dismiss_btn.setMinimumHeight(42)
        dismiss_btn.setFixedWidth(46)
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.clicked.connect(self.close)

        btn_row.addWidget(done_btn,    2)
        btn_row.addWidget(snooze_btn,  2)
        btn_row.addWidget(dismiss_btn, 0)
        root.addLayout(btn_row)

    # ── Animation ticker ─────────────────────────────────────────────────────

    def _tick(self) -> None:
        self._phase = (self._phase + 1.4) % 360.0   # full rotation in ~4.3 s
        self._pulse += 0.055                          # glow pulse cycle
        self.update()

    # ── Custom painting ───────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        full   = QRectF(self.rect())
        bw     = _BORDER_W
        inner  = full.adjusted(bw, bw, -bw, -bw)
        ri     = _RADIUS - bw          # inner corner radius
        A, B, *rest = self._palette
        C = rest[0] if rest else A
        D = rest[1] if len(rest) > 1 else B

        # ── 1. Animated conical-gradient border ring ──────────────────────
        cx, cy = full.center().x(), full.center().y()
        cg = QConicalGradient(cx, cy, self._phase)
        cg.setColorAt(0.00, _c(A, 255))
        cg.setColorAt(0.25, _c(B, 255))
        cg.setColorAt(0.50, _c(C, 255))
        cg.setColorAt(0.75, _c(D, 220))
        cg.setColorAt(1.00, _c(A, 255))

        outer_path  = QPainterPath()
        outer_path.addRoundedRect(full.adjusted(0.5, 0.5, -0.5, -0.5), _RADIUS, _RADIUS)
        inner_path  = QPainterPath()
        inner_path.addRoundedRect(inner, ri, ri)
        border_ring = outer_path.subtracted(inner_path)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(cg))
        p.drawPath(border_ring)

        # ── 2. Inner background (opaque so widgets are readable) ──────────
        clip = QPainterPath()
        clip.addRoundedRect(inner, ri, ri)
        p.setClipPath(clip)

        # Use CompositionMode_Source to write solid alpha on transparent window
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        if self._is_dark:
            bg = _DARK_BASES[self._seed % len(_DARK_BASES)]
            p.fillRect(inner, QColor(bg.red(), bg.green(), bg.blue(), 238))
        else:
            p.fillRect(inner, QColor(255, 252, 248, 240))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        # ── 3. Subtle pulsing glow overlay (palette-tinted) ───────────────
        pulse_a = int(22 + 16 * math.sin(self._pulse))
        gx = inner.left() + inner.width()  * 0.12
        gy = inner.top()  + inner.height() * 0.18
        gr = max(inner.width(), inner.height()) * 1.0
        glow = QRadialGradient(gx, gy, gr)
        glow.setColorAt(0.0, _c(A, pulse_a + 18))
        glow.setColorAt(0.4, _c(B, pulse_a))
        glow.setColorAt(1.0, _c(C, max(0, pulse_a - 8)))
        p.fillPath(clip, QBrush(glow))

        # ── 4. Second glow from opposite corner (depth effect) ────────────
        gx2 = inner.right()  - inner.width()  * 0.12
        gy2 = inner.bottom() - inner.height() * 0.18
        gr2 = max(inner.width(), inner.height()) * 0.7
        glow2 = QRadialGradient(gx2, gy2, gr2)
        glow2.setColorAt(0.0, _c(D, pulse_a + 10))
        glow2.setColorAt(1.0, _c(D, 0))
        p.fillPath(clip, QBrush(glow2))

        # painter ends automatically when it goes out of scope

    # ── Business logic ────────────────────────────────────────────────────────

    def _mark_done(self) -> None:
        with get_session() as session:
            reminder = session.get(Reminder, self._reminder_id)
            if reminder:
                reminder.is_done     = True
                reminder.is_active   = False
        self._scheduler.remove_reminder(self._reminder_id)
        self.close()

    def _snooze(self) -> None:
        snooze_until = datetime.utcnow() + timedelta(minutes=30)
        reminder     = None
        with get_session() as session:
            reminder = session.get(Reminder, self._reminder_id)
            if reminder:
                reminder.snooze_until = snooze_until
                reminder.next_trigger = snooze_until
                session.expunge(reminder)
            else:
                reminder = None
        if reminder:
            from remindee.models.reminder import FrequencyType
            reminder.frequency        = FrequencyType.SPECIFIC
            reminder.specific_datetime = snooze_until
            self._scheduler.schedule_reminder(reminder)
        self.close()

    def closeEvent(self, event) -> None:
        self._anim.stop()
        self._on_close_cb(self._reminder_id)
        super().closeEvent(event)
