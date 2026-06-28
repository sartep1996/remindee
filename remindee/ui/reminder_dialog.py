from __future__ import annotations

import random
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QDate, QTime, QPropertyAnimation, QEasingCurve, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QStandardItem, QStandardItemModel
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
from remindee.ui.reminder_card import _SCHEMES, _DARK_BASES, _STYLES, _draw_base

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

_FONT_GROUPS = [
    ("Funky & Handwritten", [
        "Marker Felt",
        "Chalkboard SE",
        "Bradley Hand",
        "Zapfino",
        "Papyrus",
        "Trattatello",
        "Herculanum",
        "Phosphate",
    ]),
    ("Traditional & Formal", [
        "Times New Roman",
        "Baskerville",
        "Palatino",
        "Didot",
        "American Typewriter",
        "Copperplate",
        "Optima",
        "Georgia",
    ]),
    ("Clean & Modern", [
        "Helvetica Neue",
        "Futura",
        "Courier New",
    ]),
]

# Flat list of selectable font names (no headers)
_FONT_OPTIONS = [f for _, fonts in _FONT_GROUPS for f in fonts]


class ReminderDialog(QDialog):
    reminder_saved = Signal(object)  # Reminder

    def __init__(
        self,
        user: "User",
        scheduler: "SchedulerService",
        reminder: Optional[Reminder] = None,
        prefill_name: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._user        = user
        self._scheduler   = scheduler
        self._reminder    = reminder
        self._edit_mode   = reminder is not None
        self._prefill_name = prefill_name

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
        self._art_dark    = (seed * 11 + 5) % 5 == 0   # mirrors card logic exactly
        self._art_style   = (seed * 17 + 5) % len(_STYLES)  # same style as card

        self.setAutoFillBackground(False)
        self.setObjectName("ReminderDialog")
        self.setWindowTitle("Edit Reminder" if self._edit_mode else "New Reminder")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build()
        if self._edit_mode:
            self._populate()
        elif self._prefill_name:
            self._name_edit.setText(self._prefill_name)

    # ── Custom background ─────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r   = QRectF(self.rect())
        rng = random.Random(self._art_seed)

        # ── Base fill — matches card exactly ─────────────────────────────
        if self._art_dark:
            base = _DARK_BASES[self._art_seed % len(_DARK_BASES)]
            p.fillRect(r, QColor(base.red(), base.green(), base.blue(), 255))
        else:
            p.fillRect(r, QColor(255, 252, 248, 255))
            _draw_base(p, r, rng, self._art_palette, self._art_seed)

        # ── Same primary style as the card ────────────────────────────────
        _STYLES[self._art_style](p, r, rng, self._art_palette)

        # ── Frosted veil — heavier than card so form fields stay readable ─
        # Dark cards: semi-transparent black (text overridden to light in _build)
        # Light cards: semi-transparent white
        if self._art_dark:
            p.fillRect(r, QColor(0, 0, 0, 148))
        else:
            p.fillRect(r, QColor(255, 255, 255, 168))

    # ── Layout ────────────────────────────────────────────────────────────────

    # ── Text-colour helpers for dark cards ───────────────────────────────────

    def _text_ss(self, size: int = 13, bold: bool = False) -> str:
        """Return a stylesheet string appropriate for the current dark/light mode."""
        if self._art_dark:
            color = "rgba(238,222,205,0.97)"
        else:
            color = "#1C0800"
        weight = "font-weight: 700;" if bold else ""
        return f"color: {color}; font-size: {size}px; {weight}"

    def _label_ss(self) -> str:
        """FormLabel style — slightly dimmer secondary colour."""
        if self._art_dark:
            return "color: rgba(195,172,148,0.90); font-size: 12px; font-weight: 600; letter-spacing: 0.3px;"
        return "color: #1C0800; font-size: 12px; font-weight: 600; letter-spacing: 0.3px;"

    def _input_ss(self, height: str = "") -> str:
        """Explicit input style for both dark and light card art.

        Non-dark cards always get a white-opaque background + near-black text
        so they stay readable regardless of the app theme — the card veil is
        always light for non-dark art, making QSS dark-mode tokens invisible.
        """
        h = f" min-height: {height};" if height else ""
        if self._art_dark:
            return (
                f"background: rgba(255,255,255,0.10); border: 1.5px solid rgba(255,255,255,0.18);"
                f"border-radius: 10px; color: rgba(238,222,205,0.97); font-size: 14px;"
                f" padding: 11px 14px;{h}"
            )
        return (
            f"background: rgba(255,255,255,0.82); border: 1.5px solid rgba(255,107,53,0.22);"
            f"border-radius: 10px; color: #1C0800; font-size: 14px;"
            f" padding: 11px 14px;{h}"
        )

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        A = self._art_palette[0]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        # Title + palette accent bar
        title_lbl = QLabel("Edit Reminder" if self._edit_mode else "New Reminder")
        title_lbl.setObjectName("DialogTitle")
        title_lbl.setStyleSheet(self._text_ss(size=20, bold=True))
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
        name_header = QHBoxLayout()
        name_header.addWidget(self._lbl("Reminder Name *"))
        name_header.addStretch()

        # Font picker — compact dropdown, right-aligned in the name header
        self._font_combo = QComboBox()
        self._font_combo.setObjectName("FontPicker")
        self._font_combo.setFixedWidth(160)
        self._font_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        font_model = QStandardItemModel()
        for group_name, fonts in _FONT_GROUPS:
            header = QStandardItem(f"  {group_name}")
            header.setEnabled(False)
            header.setFont(QFont("Helvetica Neue", 10))
            font_model.appendRow(header)
            for f in fonts:
                item = QStandardItem(f"  {f}")
                item.setFont(QFont(f, 13))
                item.setData(f, Qt.ItemDataRole.UserRole)
                font_model.appendRow(item)
        self._font_combo.setModel(font_model)
        self._font_combo.setCurrentIndex(1)  # first real font, skip group header
        self._font_combo.currentIndexChanged.connect(self._on_font_changed)
        self._on_font_changed(1)
        if self._art_dark:
            self._font_combo.setStyleSheet(
                "QComboBox { background: rgba(255,255,255,0.10); border: 1.5px solid rgba(255,255,255,0.18);"
                " border-radius: 8px; color: rgba(238,222,205,0.97); font-size: 13px; padding: 5px 10px; }"
                "QComboBox QAbstractItemView { background: rgba(28,18,42,0.97); color: rgba(238,222,205,0.97);"
                " selection-background-color: rgba(255,255,255,0.20); border-radius: 8px; padding: 4px; }"
            )
        else:
            self._font_combo.setStyleSheet(
                "QComboBox { background: rgba(255,255,255,0.82); border: 1.5px solid rgba(255,107,53,0.22);"
                " border-radius: 8px; color: #1C0800; font-size: 13px; padding: 5px 10px; }"
                "QComboBox QAbstractItemView { background: rgba(255,252,248,0.97); color: #1C0800;"
                " selection-background-color: #FF6B35; selection-color: white;"
                " border-radius: 8px; padding: 4px; }"
            )
        name_header.addWidget(self._font_combo)
        layout.addLayout(name_header)

        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("FormInput")
        self._name_edit.setPlaceholderText("What do you want to be reminded of?")
        self._name_edit.setStyleSheet(self._input_ss())
        # Enter in name field → save (not Qt dialog default-accept)
        self._name_edit.returnPressed.connect(self._save)
        layout.addWidget(self._name_edit)

        # Details
        layout.addWidget(self._lbl("More Details"))
        self._details_edit = QTextEdit()
        self._details_edit.setObjectName("DetailsEdit")
        self._details_edit.setPlaceholderText("Optional notes…")
        self._details_edit.setFixedHeight(84)
        if self._art_dark:
            self._details_edit.setStyleSheet(
                "background: rgba(255,255,255,0.10); border: 1.5px solid rgba(255,255,255,0.18);"
                "border-radius: 10px; color: rgba(238,222,205,0.97); font-size: 14px; padding: 10px;"
            )
        else:
            self._details_edit.setStyleSheet(
                "background: rgba(255,255,255,0.82); border: 1.5px solid rgba(255,107,53,0.22);"
                "border-radius: 10px; color: #1C0800; font-size: 14px; padding: 10px;"
            )
        layout.addWidget(self._details_edit)

        # Frequency
        layout.addWidget(self._lbl("Frequency *"))
        self._freq_combo = QComboBox()
        self._freq_combo.setObjectName("FreqCombo")
        for label, _ in _FREQ_OPTIONS:
            self._freq_combo.addItem(label)
        self._freq_combo.currentIndexChanged.connect(self._on_freq_changed)
        if self._art_dark:
            self._freq_combo.setStyleSheet(
                "QComboBox { background: rgba(255,255,255,0.10); border: 1.5px solid rgba(255,255,255,0.18);"
                " border-radius: 10px; color: rgba(238,222,205,0.97); font-size: 14px; padding: 10px 14px; }"
                "QComboBox QAbstractItemView { background: rgba(28,18,42,0.97); color: rgba(238,222,205,0.97);"
                " selection-background-color: rgba(255,255,255,0.20); border-radius: 8px; padding: 4px; }"
            )
        else:
            self._freq_combo.setStyleSheet(
                "QComboBox { background: rgba(255,255,255,0.82); border: 1.5px solid rgba(255,107,53,0.22);"
                " border-radius: 10px; color: #1C0800; font-size: 14px; padding: 10px 14px; }"
                "QComboBox QAbstractItemView { background: rgba(255,252,248,0.97); color: #1C0800;"
                " selection-background-color: #FF6B35; selection-color: white;"
                " border-radius: 8px; padding: 4px; }"
            )
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
        if self._art_dark:
            self._time_edit.setStyleSheet(
                "background: rgba(255,255,255,0.10); border: 1.5px solid rgba(255,255,255,0.18);"
                "border-radius: 10px; color: rgba(238,222,205,0.97); font-size: 14px; padding: 9px 14px;"
            )
        else:
            self._time_edit.setStyleSheet(
                "background: rgba(255,255,255,0.82); border: 1.5px solid rgba(255,107,53,0.22);"
                "border-radius: 10px; color: #1C0800; font-size: 14px; padding: 9px 14px;"
            )
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
        if self._art_dark:
            self._error_lbl.setStyleSheet("color: rgba(255,120,100,0.95); font-size: 12px; font-weight: 500;")
        else:
            self._error_lbl.setStyleSheet("color: #EF4444; font-size: 12px; font-weight: 500;")
        layout.addWidget(self._error_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setMinimumHeight(44)
        cancel_btn.setAutoDefault(False)   # must NOT steal Enter
        cancel_btn.clicked.connect(self.reject)
        if self._art_dark:
            cancel_btn.setStyleSheet(
                "background: rgba(255,255,255,0.12); border: 1.5px solid rgba(255,255,255,0.22);"
                "border-radius: 10px; color: rgba(238,222,205,0.90); font-size: 14px; padding: 12px;"
            )
        else:
            cancel_btn.setStyleSheet(
                "background: rgba(255,255,255,0.65); border: 1.5px solid rgba(255,107,53,0.22);"
                "border-radius: 10px; color: #1C0800; font-size: 14px; padding: 12px;"
            )
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
        lbl.setStyleSheet(self._label_ss())
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

    # ── Font picker ───────────────────────────────────────────────────────────

    def _on_font_changed(self, index: int) -> None:
        font_name = self._font_combo.currentData(Qt.ItemDataRole.UserRole)
        if font_name:
            self._font_combo.setFont(QFont(font_name, 13))

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

        font = r.font_family or "Marker Felt"
        model = self._font_combo.model()
        for i in range(model.rowCount()):
            if model.item(i) and model.item(i).data(Qt.ItemDataRole.UserRole) == font:
                self._font_combo.setCurrentIndex(i)
                self._on_font_changed(i)
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
                reminder.font_family       = (self._font_combo.currentData(Qt.ItemDataRole.UserRole) or "Marker Felt")
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
                    font_family        = self._font_combo.currentText(),
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
