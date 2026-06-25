from __future__ import annotations

import random
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QDate, QTime, QPropertyAnimation, QEasingCurve, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QRadialGradient
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
    QSizePolicy,
)

from remindee.models.reminder import Reminder, FrequencyType
from remindee.utils.database import get_session
from remindee.ui.styles import apply_calendar_palette
from remindee.ui.reminder_card import _SCHEMES, _c, _draw_base

if TYPE_CHECKING:
    from remindee.services.scheduler_service import SchedulerService
    from remindee.models.user import User

_FREQ_OPTIONS = [
    ("Often (every hour)",    FrequencyType.OFTEN),
    ("Medium (every 6 hours)", FrequencyType.MEDIUM),
    ("Rarely (daily)",        FrequencyType.RARELY),
    ("Random",                FrequencyType.RANDOM),
    ("Specific Date & Time",  FrequencyType.SPECIFIC),
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
        self._user      = user
        self._scheduler = scheduler
        self._reminder  = reminder
        self._edit_mode = reminder is not None

        # ── Art palette ───────────────────────────────────────────────────
        # In edit mode use the same seed as the card so the palette matches.
        # In create mode derive a stable seed from the user so new-reminder
        # dialogs always look the same for a given user.
        if reminder is not None and reminder.id:
            seed = reminder.id & 0x7FFFFFFF
        else:
            uid  = getattr(user, "id", None) or 0
            seed = (uid * 1_337 + 42) & 0x7FFFFFFF or 5
        self._art_seed    = seed
        self._art_palette = _SCHEMES[seed % len(_SCHEMES)]

        # The dialog always uses a LIGHT frosted veil so form fields remain
        # readable regardless of the reminder's dark/light art setting.
        self._art_rng = random.Random(seed)

        self.setAutoFillBackground(False)
        self.setObjectName("ReminderDialog")
        self.setWindowTitle("Edit Reminder" if self._edit_mode else "New Reminder")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build()
        if self._edit_mode:
            self._populate()

    # ── Custom background ─────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = QRectF(self.rect())
        A, B, *rest = self._art_palette
        C = rest[0] if rest else A
        D = rest[1] if len(rest) > 1 else B

        # Solid warm white base
        p.fillRect(r, QColor(255, 252, 248, 255))

        # Palette-tinted multi-stop gradient layer
        _draw_base(p, r, random.Random(self._art_seed), self._art_palette, self._art_seed)

        # Accent glow — top-right corner
        p.setPen(Qt.NoPen)
        cx  = r.right() - r.width()  * 0.12
        cy  = r.top()   + r.height() * 0.20
        gr  = max(r.width(), r.height()) * 0.58
        g1  = QRadialGradient(cx, cy, gr)
        g1.setColorAt(0.0, _c(A, 72))
        g1.setColorAt(0.5, _c(B, 32))
        g1.setColorAt(1.0, _c(A, 0))
        p.setBrush(QBrush(g1))
        p.drawEllipse(QPointF(cx, cy), gr, gr)

        # Accent glow — bottom-left corner
        cx2 = r.left()   + r.width()  * 0.08
        cy2 = r.bottom() - r.height() * 0.14
        gr2 = max(r.width(), r.height()) * 0.42
        g2  = QRadialGradient(cx2, cy2, gr2)
        g2.setColorAt(0.0, _c(D, 55))
        g2.setColorAt(1.0, _c(D, 0))
        p.setBrush(QBrush(g2))
        p.drawEllipse(QPointF(cx2, cy2), gr2, gr2)

        # Heavy white veil — keeps all form fields clearly readable
        p.fillRect(r, QColor(255, 255, 255, 178))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        A = self._art_palette[0]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        # Title + palette accent bar
        title_lbl = QLabel("Edit Reminder" if self._edit_mode else "New Reminder")
        title_lbl.setObjectName("DialogTitle")
        layout.addWidget(title_lbl)

        accent_bar = QLabel()
        accent_bar.setFixedHeight(3)
        accent_bar.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 rgba({A.red()},{A.green()},{A.blue()},220),"
            f"stop:1 rgba({A.red()},{A.green()},{A.blue()},0));"
            f"border-radius: 2px;"
        )
        layout.addWidget(accent_bar)
        layout.addSpacing(4)

        # Name
        layout.addWidget(self._lbl("Reminder Name *"))
        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("FormInput")
        self._name_edit.setPlaceholderText("What do you want to be reminded of?")
        # Enter in name field → save (not Qt dialog default-accept)
        self._name_edit.returnPressed.connect(self._save)
        layout.addWidget(self._name_edit)

        # Details
        layout.addWidget(self._lbl("More Details"))
        self._details_edit = QTextEdit()
        self._details_edit.setObjectName("DetailsEdit")
        self._details_edit.setPlaceholderText("Optional notes…")
        self._details_edit.setFixedHeight(84)
        layout.addWidget(self._details_edit)

        # Frequency
        layout.addWidget(self._lbl("Frequency *"))
        self._freq_combo = QComboBox()
        self._freq_combo.setObjectName("FreqCombo")
        for label, _ in _FREQ_OPTIONS:
            self._freq_combo.addItem(label)
        self._freq_combo.currentIndexChanged.connect(self._on_freq_changed)
        layout.addWidget(self._freq_combo)

        # Collapsible date/time panel (shown only for Specific)
        self._dt_widget = QWidget()
        self._dt_widget.setObjectName("DateTimeWidget")
        dt_layout = QVBoxLayout(self._dt_widget)
        dt_layout.setContentsMargins(0, 0, 0, 0)
        dt_layout.setSpacing(8)

        dt_layout.addWidget(self._lbl("Date"))
        self._calendar = QCalendarWidget()
        self._calendar.setGridVisible(False)
        self._calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        apply_calendar_palette(self._calendar, self._user.theme)
        dt_layout.addWidget(self._calendar)

        dt_layout.addWidget(self._lbl("Time"))
        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setTime(QTime.currentTime())
        dt_layout.addWidget(self._time_edit)

        self._dt_widget.setMaximumHeight(0)
        self._dt_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self._dt_widget)

        # Error label
        self._error_lbl = QLabel("")
        self._error_lbl.setObjectName("ErrorLabel")
        self._error_lbl.hide()
        layout.addWidget(self._error_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setMinimumHeight(44)
        cancel_btn.setAutoDefault(False)   # must NOT steal Enter
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save Reminder")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setMinimumHeight(44)
        save_btn.setDefault(True)          # Enter triggers this button
        save_btn.setAutoDefault(True)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FormLabel")
        return lbl

    # ── Keyboard ──────────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Enter in QTextEdit should insert a newline, not save
            if not self._details_edit.hasFocus():
                self._save()
                return
        elif key == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    # ── Date/time panel animation ─────────────────────────────────────────────

    def _on_freq_changed(self, index: int) -> None:
        _, freq_type = _FREQ_OPTIONS[index]
        show = freq_type == FrequencyType.SPECIFIC
        target = 420 if show else 0

        anim = QPropertyAnimation(self._dt_widget, b"maximumHeight")
        anim.setDuration(250)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim.setStartValue(self._dt_widget.maximumHeight())
        anim.setEndValue(target)
        if show:
            anim.finished.connect(self.adjustSize)
        anim.start()
        self._anim = anim

    # ── Populate (edit mode) ──────────────────────────────────────────────────

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
            self._calendar.setSelectedDate(
                QDate(r.specific_datetime.year,
                      r.specific_datetime.month,
                      r.specific_datetime.day)
            )
            self._time_edit.setTime(
                QTime(r.specific_datetime.hour, r.specific_datetime.minute)
            )
            self._dt_widget.setMaximumHeight(420)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            self._show_error("Reminder name is required.")
            return

        _, freq_type = _FREQ_OPTIONS[self._freq_combo.currentIndex()]
        specific_dt: Optional[datetime] = None

        if freq_type == FrequencyType.SPECIFIC:
            qdate       = self._calendar.selectedDate()
            qtime       = self._time_edit.time()
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
                reminder.name              = name
                reminder.details           = details
                reminder.frequency         = freq_type
                reminder.specific_datetime = specific_dt
                reminder.is_done           = False
                reminder.is_active         = True
                session.flush()
                session.refresh(reminder)
                session.expunge(reminder)
            else:
                reminder = Reminder(
                    user_id            = self._user.id,
                    name               = name,
                    details            = details,
                    frequency          = freq_type,
                    specific_datetime  = specific_dt,
                    is_active          = True,
                    is_done            = False,
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
