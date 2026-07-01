from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QDate, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QTextCursor
from PySide6.QtWidgets import (
    QCalendarWidget, QCheckBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from remindee.models.task import Task
from remindee.models.user import User
from remindee.services.task_service import TaskService
from remindee.ui.reminder_card import (
    _DARK_BASES, _SCHEMES, _STYLES, _draw_base,
)


class _DatePickerDialog(QDialog):
    """Standalone calendar + time picker — avoids QDateTimeEdit popup issues on macOS."""

    def __init__(self, initial: Optional[datetime] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pick a date & time")
        self.setModal(True)
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        self._cal = QCalendarWidget()
        self._cal.setGridVisible(True)
        self._cal.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        if initial:
            self._cal.setSelectedDate(QDate(initial.year, initial.month, initial.day))
        layout.addWidget(self._cal)

        time_row = QHBoxLayout()
        time_row.setSpacing(6)
        time_row.addWidget(QLabel("Time:"))

        self._hour = QSpinBox()
        self._hour.setRange(0, 23)
        self._hour.setValue(initial.hour if initial else 9)
        self._hour.setFixedWidth(52)
        time_row.addWidget(self._hour)

        time_row.addWidget(QLabel(":"))

        self._minute = QSpinBox()
        self._minute.setRange(0, 59)
        self._minute.setValue(initial.minute if initial else 0)
        self._minute.setSingleStep(5)
        self._minute.setFixedWidth(52)
        time_row.addWidget(self._minute)

        time_row.addStretch()
        layout.addLayout(time_row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_datetime(self) -> datetime:
        qd = self._cal.selectedDate()
        return datetime(qd.year(), qd.month(), qd.day(),
                        self._hour.value(), self._minute.value(), 0)


class TaskDialog(QDialog):
    """Create / edit a task.

    The body text area is the single editing surface — plain lines are the
    description, lines prefixed with '[ ] ' or '[x] ' are subtasks.
    Clicking '☐ Make subtask' toggles the prefix on the current line or
    every selected line.
    """

    task_saved = Signal(object)  # Task

    def __init__(
        self,
        user: User,
        task_service: TaskService,
        task: Optional[Task] = None,
        scheduler=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._user         = user
        self._task_service = task_service
        self._task         = task
        self._scheduler    = scheduler

        # Art seed mirrors TaskCard
        if task and task.id:
            seed = task.id & 0x7FFFFFFF
        else:
            uid  = getattr(user, "id", None) or 0
            seed = (uid * 2_741 + 17) & 0x7FFFFFFF or 7
        self._art_seed  = seed
        self._art_dark  = (seed * 11 + 5) % 5 == 0
        self._art_pal   = _SCHEMES[seed % len(_SCHEMES)]
        self._art_style = (seed * 17 + 5) % len(_STYLES)

        self.setAutoFillBackground(False)
        self.setObjectName("TaskDialog")
        self.setWindowTitle("Edit Task" if task else "New Task")
        self.setMinimumSize(480, 480)
        self.resize(540, 580)
        self.setModal(True)

        self._due_datetime: Optional[datetime] = None
        self._reminder_datetime: Optional[datetime] = None

        self._build()

        if task:
            self._title_edit.setText(task.title or "")
            if task.due_date:
                dt = task.due_date.replace(tzinfo=None) if task.due_date.tzinfo else task.due_date
                self._due_datetime = dt
                self._due_check.setChecked(True)
                self._due_btn.setText(dt.strftime("%b %d %Y  %H:%M"))
                self._due_btn.setEnabled(True)
            # Merge description + existing subtasks into unified body
            body_lines: list[str] = []
            if task.description:
                body_lines.extend(task.description.split('\n'))
            for sub in TaskService.parse_subtasks(task):
                prefix = '[x] ' if sub.get('done') else '[ ] '
                body_lines.append(prefix + sub.get('title', ''))
            if body_lines:
                self._body_edit.setPlainText('\n'.join(body_lines))

        self._title_edit.setFocus()

    # ── Background art ────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r   = QRectF(self.rect())
        rng = random.Random(self._art_seed)

        if self._art_dark:
            base = _DARK_BASES[self._art_seed % len(_DARK_BASES)]
            p.fillRect(r, QColor(base.red(), base.green(), base.blue(), 255))
        else:
            p.fillRect(r, QColor(255, 252, 248, 255))
            _draw_base(p, r, rng, self._art_pal, self._art_seed)

        _STYLES[self._art_style](p, r, rng, self._art_pal)

        if self._art_dark:
            p.fillRect(r, QColor(0, 0, 0, 148))
        else:
            p.fillRect(r, QColor(255, 255, 255, 155))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _tc(self) -> str:
        return "rgba(238,222,205,0.97)" if self._art_dark else "#1C0800"

    def _input_ss(self) -> str:
        if self._art_dark:
            return (
                "background: rgba(255,255,255,0.10);"
                " border: 1.5px solid rgba(255,255,255,0.18);"
                " border-radius: 10px; color: rgba(238,222,205,0.97);"
                " font-size: 14px; padding: 9px 14px;"
            )
        return (
            "background: rgba(255,255,255,0.82);"
            " border: 1.5px solid rgba(255,107,53,0.22);"
            " border-radius: 10px; color: #1C0800;"
            " font-size: 14px; padding: 9px 14px;"
        )

    def _btn_ss(self, primary: bool = False) -> str:
        if primary:
            return (
                "QPushButton { background: #FF6B35; border: none; border-radius: 9px;"
                " font-size: 13px; font-weight: 700; color: white; padding: 0 20px; }"
                "QPushButton:hover { background: #E85A25; }"
            )
        if self._art_dark:
            return (
                "QPushButton { background: rgba(255,255,255,0.10);"
                " border: 1.5px solid rgba(255,255,255,0.22); border-radius: 9px;"
                " font-size: 13px; color: rgba(238,222,205,0.90); padding: 0 16px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.20); }"
            )
        return (
            "QPushButton { background: rgba(255,255,255,0.70);"
            " border: 1.5px solid rgba(0,0,0,0.15); border-radius: 9px;"
            " font-size: 13px; color: #2C0E00; padding: 0 16px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.90); }"
        )

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_content(), stretch=1)
        root.addWidget(self._build_bottom())

    def _build_content(self) -> QWidget:
        pane = QWidget()
        pane.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(28, 24, 28, 8)
        layout.setSpacing(10)

        # Title
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Task name…")
        self._title_edit.setFont(QFont("Marker Felt", 16, QFont.Weight.Bold))
        self._title_edit.setStyleSheet(
            f"QLineEdit {{ {self._input_ss()} font-size: 18px; font-weight: 700; }}"
            f"QLineEdit:focus {{ border-color: {'rgba(255,255,255,0.40)' if self._art_dark else '#FF6B35'}; }}"
        )
        layout.addWidget(self._title_edit)

        # Body header
        body_hdr = QHBoxLayout()
        body_hdr.setSpacing(8)
        body_lbl = QLabel("Notes & subtasks")
        body_lbl.setStyleSheet(
            f"background: transparent; color: {self._tc()}; font-size: 13px; font-weight: 600;"
        )
        body_hdr.addWidget(body_lbl)
        body_hdr.addStretch()

        if self._art_dark:
            chip_ss = (
                "QPushButton { background: rgba(255,107,53,0.18);"
                " border: 1.5px solid rgba(255,107,53,0.45); border-radius: 12px;"
                " font-size: 12px; font-weight: 600;"
                " color: rgba(255,160,100,0.95); padding: 0 13px; }"
                "QPushButton:hover { background: rgba(255,107,53,0.32);"
                " border-color: rgba(255,107,53,0.70); }"
                "QPushButton:pressed { background: rgba(255,107,53,0.44); }"
            )
        else:
            chip_ss = (
                "QPushButton { background: rgba(255,107,53,0.10);"
                " border: 1.5px solid rgba(255,107,53,0.38); border-radius: 12px;"
                " font-size: 12px; font-weight: 600;"
                " color: #E85A20; padding: 0 13px; }"
                "QPushButton:hover { background: rgba(255,107,53,0.22);"
                " border-color: rgba(255,107,53,0.65); }"
                "QPushButton:pressed { background: rgba(255,107,53,0.32); }"
            )

        self._to_subtask_btn = QPushButton("☑  subtask")
        self._to_subtask_btn.setFixedHeight(28)
        self._to_subtask_btn.setToolTip(
            "Toggle [ ] / [x] subtask prefix on the current line or selection"
        )
        self._to_subtask_btn.setStyleSheet(chip_ss)
        self._to_subtask_btn.clicked.connect(self._toggle_subtask_line)
        body_hdr.addWidget(self._to_subtask_btn)
        layout.addLayout(body_hdr)

        # Body — fills available space; [ ] / [x] lines are subtasks
        self._body_edit = QTextEdit()
        self._body_edit.setPlaceholderText(
            "Write notes here…\n\n"
            "Select any line and click ☐ Make subtask to turn it into a checklist item.\n"
            "Or type  [ ] item text  yourself."
        )
        self._body_edit.setMinimumHeight(180)
        desc_focus = "rgba(255,255,255,0.40)" if self._art_dark else "#FF6B35"
        if self._art_dark:
            self._body_edit.setStyleSheet(
                "QTextEdit { background: rgba(255,255,255,0.08);"
                " border: 1.5px solid rgba(255,255,255,0.18); border-radius: 10px;"
                " color: rgba(238,222,205,0.97); font-size: 13px; padding: 9px 12px; }"
                f"QTextEdit:focus {{ border-color: {desc_focus}; }}"
            )
        else:
            self._body_edit.setStyleSheet(
                "QTextEdit { background: rgba(255,255,255,0.82);"
                " border: 1.5px solid rgba(255,107,53,0.22); border-radius: 10px;"
                " color: #1C0800; font-size: 13px; padding: 9px 12px; }"
                f"QTextEdit:focus {{ border-color: {desc_focus}; }}"
            )
        layout.addWidget(self._body_edit, stretch=1)

        # Due date row
        due_row = QHBoxLayout()
        due_row.setSpacing(10)
        self._due_check = QCheckBox("Due date:")
        self._due_check.setStyleSheet(
            f"QCheckBox {{ background: transparent; color: {self._tc()}; font-size: 13px; }}"
        )
        due_row.addWidget(self._due_check)

        self._due_btn = QPushButton("📅  Pick date & time")
        self._due_btn.setEnabled(False)
        self._due_btn.setFixedHeight(38)
        self._due_btn.setStyleSheet(
            f"QPushButton {{ {self._input_ss()} text-align: left; }}"
            f"QPushButton:disabled {{ opacity: 0.45; }}"
            f"QPushButton:hover:enabled {{ border-color: "
            f"{'rgba(255,255,255,0.40)' if self._art_dark else '#FF6B35'}; }}"
        )
        self._due_btn.clicked.connect(self._pick_due_date)
        due_row.addWidget(self._due_btn, stretch=1)
        self._due_check.toggled.connect(self._on_due_check_toggled)
        layout.addLayout(due_row)

        # Reminder row (only when scheduler is provided)
        if self._scheduler is not None:
            reminder_row = QHBoxLayout()
            reminder_row.setSpacing(10)
            self._reminder_check = QCheckBox("🔔 Reminder:")
            self._reminder_check.setStyleSheet(
                f"QCheckBox {{ background: transparent; color: {self._tc()}; font-size: 13px; }}"
            )
            reminder_row.addWidget(self._reminder_check)

            self._reminder_btn = QPushButton("🔔  Pick reminder time")
            self._reminder_btn.setEnabled(False)
            self._reminder_btn.setFixedHeight(38)
            self._reminder_btn.setStyleSheet(
                f"QPushButton {{ {self._input_ss()} text-align: left; }}"
                f"QPushButton:disabled {{ opacity: 0.45; }}"
                f"QPushButton:hover:enabled {{ border-color: "
                f"{'rgba(255,255,255,0.40)' if self._art_dark else '#FF6B35'}; }}"
            )
            self._reminder_btn.clicked.connect(self._pick_reminder_time)
            reminder_row.addWidget(self._reminder_btn, stretch=1)
            self._reminder_check.toggled.connect(self._on_reminder_check_toggled)
            layout.addLayout(reminder_row)

        return pane

    def _build_bottom(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        if self._art_dark:
            bar.setStyleSheet(
                "background: rgba(0,0,0,0.25);"
                " border-top: 1px solid rgba(255,255,255,0.10);"
            )
        else:
            bar.setStyleSheet(
                "background: rgba(255,255,255,0.30);"
                " border-top: 1px solid rgba(0,0,0,0.08);"
            )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)
        layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.setStyleSheet(self._btn_ss(primary=False))
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.setFixedHeight(36)
        save_btn.setMinimumWidth(80)
        save_btn.setStyleSheet(self._btn_ss(primary=True))
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        return bar

    # ── Body / subtask toggle ─────────────────────────────────────────────────

    def _toggle_subtask_line(self) -> None:
        """Toggle [ ] / [x] prefix on the current line or every selected line."""
        cursor = self._body_edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)

        selected = cursor.selectedText()
        if not selected.strip():
            return

        # QTextEdit uses U+2029 (paragraph separator) between lines in selectedText()
        lines = selected.replace(' ', '\n').split('\n')
        new_lines = []
        for line in lines:
            if line.startswith('[ ] ') or line.startswith('[x] '):
                new_lines.append(line[4:])
            else:
                new_lines.append('[ ] ' + line)
        cursor.insertText('\n'.join(new_lines))
        self._body_edit.setTextCursor(cursor)

    # ── Due date helpers ──────────────────────────────────────────────────────

    def _on_due_check_toggled(self, checked: bool) -> None:
        self._due_btn.setEnabled(checked)
        if not checked:
            self._due_datetime = None
            self._due_btn.setText("📅  Pick date & time")

    def _pick_due_date(self) -> None:
        dlg = _DatePickerDialog(initial=self._due_datetime, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._due_datetime = dlg.selected_datetime()
            self._due_btn.setText(self._due_datetime.strftime("%b %d %Y  %H:%M"))

    # ── Reminder helpers ──────────────────────────────────────────────────────

    def _on_reminder_check_toggled(self, checked: bool) -> None:
        self._reminder_btn.setEnabled(checked)
        if not checked:
            self._reminder_datetime = None
            self._reminder_btn.setText("🔔  Pick reminder time")

    def _pick_reminder_time(self) -> None:
        dlg = _DatePickerDialog(initial=self._reminder_datetime, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reminder_datetime = dlg.selected_datetime()
            self._reminder_btn.setText(self._reminder_datetime.strftime("%b %d %Y  %H:%M"))

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        title = self._title_edit.text().strip()
        if not title:
            self._title_edit.setFocus()
            return

        due_date: Optional[datetime] = None
        if self._due_check.isChecked():
            due_date = self._due_datetime

        # Parse body: lines prefixed with [ ] or [x] become subtasks
        subtasks: list[dict] = []
        desc_lines: list[str] = []
        for line in self._body_edit.toPlainText().split('\n'):
            if line.startswith('[ ] '):
                subtasks.append({'title': line[4:].strip(), 'done': False})
            elif line.startswith('[x] '):
                subtasks.append({'title': line[4:].strip(), 'done': True})
            else:
                desc_lines.append(line)
        description = '\n'.join(desc_lines).strip() or None
        subs_json = json.dumps(subtasks) if subtasks else None

        if self._task is None:
            task = self._task_service.create_task(
                self._user.id, title, due_date=due_date,
                subtasks=subtasks or None, description=description,
            )
        else:
            task = self._task_service.update_task(
                self._task.id,
                title=title,
                due_date=due_date,
                subtasks=subs_json,
                description=description,
                updated_at=datetime.utcnow(),
            )

        self.task_saved.emit(task)

        # Schedule task-level reminder
        if self._scheduler is not None:
            from remindee.models.reminder import Reminder, FrequencyType
            from remindee.utils.database import get_session

            if (getattr(self, "_reminder_check", None) is not None
                    and self._reminder_check.isChecked()
                    and self._reminder_datetime is not None):
                with get_session() as session:
                    r = Reminder(
                        user_id=self._user.id,
                        name=title,
                        frequency=FrequencyType.SPECIFIC,
                        specific_datetime=self._reminder_datetime,
                        is_active=True,
                        is_done=False,
                    )
                    session.add(r)
                    session.flush()
                    session.refresh(r)
                    session.expunge(r)
                self._scheduler.schedule_reminder(r)

        self.accept()
