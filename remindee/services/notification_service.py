from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QSystemTrayIcon,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QApplication,
)

from remindee.models.reminder import Reminder
from remindee.utils.database import get_session

if TYPE_CHECKING:
    from remindee.services.scheduler_service import SchedulerService


class NotificationService:
    def __init__(
        self,
        tray_icon: QSystemTrayIcon,
        scheduler_service: "SchedulerService",
    ) -> None:
        self._tray = tray_icon
        self._scheduler = scheduler_service
        self._active_bubbles: dict[int, "ActionBubble"] = {}

    def notify(self, reminder: Reminder) -> None:
        title = "REMINDEE"
        message = reminder.name
        if reminder.details:
            message += f"\n{reminder.details[:100]}"

        if self._tray.isSystemTrayAvailable():
            self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

        self.show_action_bubble(reminder)

    def show_action_bubble(self, reminder: Reminder) -> None:
        if reminder.id in self._active_bubbles:
            existing = self._active_bubbles[reminder.id]
            if existing.isVisible():
                existing.raise_()
                existing.activateWindow()
                return
        bubble = ActionBubble(reminder, self._scheduler, self._on_bubble_closed)
        self._active_bubbles[reminder.id] = bubble
        bubble.show()

    def _on_bubble_closed(self, reminder_id: int) -> None:
        self._active_bubbles.pop(reminder_id, None)


class ActionBubble(QDialog):
    def __init__(
        self,
        reminder: Reminder,
        scheduler: "SchedulerService",
        on_close_cb,
    ) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self._reminder_id = reminder.id
        self._scheduler = scheduler
        self._on_close_cb = on_close_cb

        self.setWindowTitle("Reminder")
        self.setFixedWidth(320)
        self.setObjectName("ActionBubble")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        name_label = QLabel(reminder.name)
        name_label.setObjectName("BubbleName")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        if reminder.details:
            detail_label = QLabel(reminder.details[:200])
            detail_label.setObjectName("BubbleDetail")
            detail_label.setWordWrap(True)
            layout.addWidget(detail_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        done_btn = QPushButton("Mark Done")
        done_btn.setObjectName("BubbleDoneBtn")
        done_btn.clicked.connect(self._mark_done)
        btn_row.addWidget(done_btn)

        snooze_btn = QPushButton("Snooze 30 min")
        snooze_btn.setObjectName("BubbleSnoozeBtn")
        snooze_btn.clicked.connect(self._snooze)
        btn_row.addWidget(snooze_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setObjectName("BubbleDismissBtn")
        dismiss_btn.clicked.connect(self.close)
        btn_row.addWidget(dismiss_btn)

        layout.addLayout(btn_row)

        # Position bottom-right of screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(
            screen.right() - self.width() - 20,
            screen.bottom() - self.height() - 20,
        )

        # Auto-dismiss after 30 seconds
        QTimer.singleShot(30_000, self.close)

    def _mark_done(self) -> None:
        with get_session() as session:
            reminder = session.get(Reminder, self._reminder_id)
            if reminder:
                reminder.is_done = True
                reminder.is_active = False
        self._scheduler.remove_reminder(self._reminder_id)
        self.close()

    def _snooze(self) -> None:
        snooze_until = datetime.utcnow() + timedelta(minutes=30)
        with get_session() as session:
            reminder = session.get(Reminder, self._reminder_id)
            if reminder:
                reminder.snooze_until = snooze_until
                reminder.next_trigger = snooze_until
                session.expunge(reminder)

        if reminder:
            from remindee.models.reminder import FrequencyType
            reminder.frequency = FrequencyType.SPECIFIC
            reminder.specific_datetime = snooze_until
            self._scheduler.schedule_reminder(reminder)
        self.close()

    def closeEvent(self, event) -> None:
        self._on_close_cb(self._reminder_id)
        super().closeEvent(event)
