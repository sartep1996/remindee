from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QSizePolicy,
)

from remindee.models.reminder import Reminder, FrequencyType

_FREQ_LABELS = {
    FrequencyType.OFTEN: "Every hour",
    FrequencyType.MEDIUM: "Every 6h",
    FrequencyType.RARELY: "Daily",
    FrequencyType.RANDOM: "Random",
    FrequencyType.SPECIFIC: "One-time",
}


class ReminderCard(QFrame):
    edit_requested = Signal(object)    # Reminder
    done_requested = Signal(object)    # Reminder
    delete_requested = Signal(object)  # Reminder

    def __init__(self, reminder: Reminder, parent=None) -> None:
        super().__init__(parent)
        self._reminder = reminder
        self.setObjectName("ReminderCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(6)

        # Top row: title + badge + actions
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

        # Details (optional)
        if self._reminder.details:
            details = QLabel(self._reminder.details[:120])
            details.setObjectName("CardDetails")
            details.setWordWrap(True)
            outer.addWidget(details)

        # Next trigger / due date
        trigger_text = self._format_trigger()
        if trigger_text:
            trigger_lbl = QLabel(trigger_text)
            trigger_lbl.setObjectName("CardTrigger")
            outer.addWidget(trigger_lbl)

    def _format_trigger(self) -> str:
        if self._reminder.frequency == FrequencyType.SPECIFIC and self._reminder.specific_datetime:
            dt = self._reminder.specific_datetime
            return f"Due: {dt.strftime('%b %d, %Y  %H:%M')}"
        if self._reminder.next_trigger:
            dt = self._reminder.next_trigger
            now = datetime.utcnow()
            delta = dt - now
            total_secs = int(delta.total_seconds())
            if total_secs < 0:
                return "Overdue"
            if total_secs < 3600:
                mins = total_secs // 60
                return f"Next: {mins}m"
            if total_secs < 86400:
                hrs = total_secs // 3600
                return f"Next: {hrs}h"
            return f"Next: {dt.strftime('%b %d')}"
        return ""

    def refresh(self, reminder: Reminder) -> None:
        self._reminder = reminder
        # Rebuild layout
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            old_layout.deleteLater()
        self._build()
