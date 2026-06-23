from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QDate, QTime, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QCalendarWidget,
    QTimeEdit,
    QPushButton,
    QWidget,
    QMessageBox,
    QSizePolicy,
    QFrame,
)

from remindee.models.reminder import Reminder, FrequencyType
from remindee.utils.database import get_session

if TYPE_CHECKING:
    from remindee.services.scheduler_service import SchedulerService
    from remindee.models.user import User

_FREQ_OPTIONS = [
    ("Often (every hour)", FrequencyType.OFTEN),
    ("Medium (every 6 hours)", FrequencyType.MEDIUM),
    ("Rarely (daily)", FrequencyType.RARELY),
    ("Random", FrequencyType.RANDOM),
    ("Specific Date & Time", FrequencyType.SPECIFIC),
]


class ReminderDialog(QDialog):
    reminder_saved = Signal(object)  # Reminder

    def __init__(
        self,
        user: "User",
        scheduler: "SchedulerService",
        reminder: Optional[Reminder] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._user = user
        self._scheduler = scheduler
        self._reminder = reminder
        self._edit_mode = reminder is not None

        self.setObjectName("ReminderDialog")
        self.setWindowTitle("Edit Reminder" if self._edit_mode else "New Reminder")
        self.setMinimumWidth(460)
        self.setModal(True)
        self._build()
        if self._edit_mode:
            self._populate()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title_lbl = QLabel("Edit Reminder" if self._edit_mode else "New Reminder")
        title_lbl.setObjectName("DialogTitle")
        layout.addWidget(title_lbl)

        # Name
        layout.addWidget(self._make_label("Reminder Name *"))
        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("FormInput")
        self._name_edit.setPlaceholderText("What do you want to be reminded of?")
        layout.addWidget(self._name_edit)

        # Details
        layout.addWidget(self._make_label("More Details"))
        self._details_edit = QTextEdit()
        self._details_edit.setObjectName("DetailsEdit")
        self._details_edit.setPlaceholderText("Optional notes…")
        self._details_edit.setFixedHeight(80)
        layout.addWidget(self._details_edit)

        # Frequency
        layout.addWidget(self._make_label("Frequency *"))
        self._freq_combo = QComboBox()
        self._freq_combo.setObjectName("FreqCombo")
        for label, _ in _FREQ_OPTIONS:
            self._freq_combo.addItem(label)
        self._freq_combo.currentIndexChanged.connect(self._on_freq_changed)
        layout.addWidget(self._freq_combo)

        # Date/time container (shown only for Specific)
        self._dt_widget = QWidget()
        self._dt_widget.setObjectName("DateTimeWidget")
        dt_layout = QVBoxLayout(self._dt_widget)
        dt_layout.setContentsMargins(0, 0, 0, 0)
        dt_layout.setSpacing(8)

        dt_layout.addWidget(self._make_label("Date"))
        self._calendar = QCalendarWidget()
        self._calendar.setGridVisible(False)
        self._calendar.setMinimumDate(QDate.currentDate())
        dt_layout.addWidget(self._calendar)

        dt_layout.addWidget(self._make_label("Time"))
        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setTime(QTime.currentTime())
        dt_layout.addWidget(self._time_edit)

        self._dt_widget.setMaximumHeight(0)
        self._dt_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._dt_widget)

        # Error label
        self._error_lbl = QLabel("")
        self._error_lbl.setObjectName("ErrorLabel")
        self._error_lbl.hide()
        layout.addWidget(self._error_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save Reminder")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FormLabel")
        return lbl

    def _on_freq_changed(self, index: int) -> None:
        _, freq_type = _FREQ_OPTIONS[index]
        show = freq_type == FrequencyType.SPECIFIC
        target_height = 370 if show else 0

        anim = QPropertyAnimation(self._dt_widget, b"maximumHeight")
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim.setStartValue(self._dt_widget.maximumHeight())
        anim.setEndValue(target_height)
        anim.start()
        self._anim = anim  # keep reference

    def _populate(self) -> None:
        r = self._reminder
        self._name_edit.setText(r.name)
        if r.details:
            self._details_edit.setPlainText(r.details)

        for i, (_, ft) in enumerate(_FREQ_OPTIONS):
            if ft == r.frequency:
                self._freq_combo.setCurrentIndex(i)
                break

        if r.frequency == FrequencyType.SPECIFIC and r.specific_datetime:
            qdate = QDate(
                r.specific_datetime.year,
                r.specific_datetime.month,
                r.specific_datetime.day,
            )
            self._calendar.setSelectedDate(qdate)
            self._time_edit.setTime(
                QTime(r.specific_datetime.hour, r.specific_datetime.minute)
            )
            self._dt_widget.setMaximumHeight(370)

    def _save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            self._show_error("Reminder name is required.")
            return

        _, freq_type = _FREQ_OPTIONS[self._freq_combo.currentIndex()]
        specific_dt: Optional[datetime] = None

        if freq_type == FrequencyType.SPECIFIC:
            qdate = self._calendar.selectedDate()
            qtime = self._time_edit.time()
            specific_dt = datetime(
                qdate.year(), qdate.month(), qdate.day(),
                qtime.hour(), qtime.minute(),
            )
            if specific_dt <= datetime.utcnow():
                self._show_error("Date and time must be in the future.")
                return

        details = self._details_edit.toPlainText().strip() or None

        with get_session() as session:
            if self._edit_mode:
                reminder = session.get(Reminder, self._reminder.id)
                if reminder is None:
                    self._show_error("Reminder not found.")
                    return
                reminder.name = name
                reminder.details = details
                reminder.frequency = freq_type
                reminder.specific_datetime = specific_dt
                reminder.is_done = False
                reminder.is_active = True
                session.flush()
                session.refresh(reminder)
                session.expunge(reminder)
            else:
                reminder = Reminder(
                    user_id=self._user.id,
                    name=name,
                    details=details,
                    frequency=freq_type,
                    specific_datetime=specific_dt,
                    is_active=True,
                    is_done=False,
                )
                session.add(reminder)
                session.flush()
                session.refresh(reminder)
                session.expunge(reminder)

        self._scheduler.schedule_reminder(reminder)
        self.reminder_saved.emit(reminder)
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_lbl.setText(msg)
        self._error_lbl.show()
