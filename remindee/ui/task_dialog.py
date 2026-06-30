from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QDateTimeEdit, QDialog, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from remindee.models.task import Task
from remindee.models.user import User
from remindee.services.task_service import TaskService
from remindee.ui.reminder_card import (
    _DARK_BASES, _SCHEMES, _STYLES, _draw_base,
)


class TaskDialog(QDialog):
    """Create / edit a task — title, optional due date, subtask list."""

    task_saved = Signal(object)  # Task

    def __init__(
        self,
        user: User,
        task_service: TaskService,
        task: Optional[Task] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._user         = user
        self._task_service = task_service
        self._task         = task

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
        self.setMinimumSize(480, 420)
        self.resize(520, 500)
        self.setModal(True)

        self._subtasks: list[dict] = (
            TaskService.parse_subtasks(task) if task else []
        )
        self._sub_rows: list[tuple[QCheckBox, QLineEdit]] = []

        self._build()

        if task:
            self._title_edit.setText(task.title or "")
            if task.due_date:
                self._due_check.setChecked(True)
                self._due_edit.setDateTime(
                    task.due_date.replace(tzinfo=None)
                    if task.due_date.tzinfo else task.due_date
                )
                self._due_edit.setEnabled(True)
            for sub in self._subtasks:
                self._add_subtask_row(sub.get("title", ""), sub.get("done", False))
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

        # Due date row
        due_row = QHBoxLayout()
        due_row.setSpacing(10)
        self._due_check = QCheckBox("Due date:")
        self._due_check.setStyleSheet(
            f"QCheckBox {{ background: transparent; color: {self._tc()}; font-size: 13px; }}"
        )
        due_row.addWidget(self._due_check)

        self._due_edit = QDateTimeEdit()
        self._due_edit.setCalendarPopup(True)
        self._due_edit.setDateTime(datetime.now().replace(second=0, microsecond=0))
        self._due_edit.setEnabled(False)
        self._due_edit.setDisplayFormat("MMM d yyyy  h:mm AP")
        self._due_edit.setStyleSheet(
            f"QDateTimeEdit {{ {self._input_ss()} }}"
            f"QDateTimeEdit:disabled {{ opacity: 0.4; }}"
        )
        due_row.addWidget(self._due_edit, stretch=1)
        self._due_check.toggled.connect(self._due_edit.setEnabled)
        layout.addLayout(due_row)

        # Subtasks label + add button
        sub_hdr = QHBoxLayout()
        sub_lbl = QLabel("Subtasks")
        sub_lbl.setStyleSheet(
            f"background: transparent; color: {self._tc()}; font-size: 13px; font-weight: 600;"
        )
        sub_hdr.addWidget(sub_lbl)
        sub_hdr.addStretch()
        add_sub_btn = QPushButton("+ Add subtask")
        add_sub_btn.setFixedHeight(28)
        add_sub_btn.setStyleSheet(self._btn_ss(primary=False))
        add_sub_btn.clicked.connect(lambda: self._add_subtask_row())
        sub_hdr.addWidget(add_sub_btn)
        layout.addLayout(sub_hdr)

        # Scrollable subtask area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 5px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(0,0,0,0.12); border-radius: 2px; }"
        )

        self._sub_container = QWidget()
        self._sub_container.setStyleSheet("background: transparent;")
        self._sub_layout = QVBoxLayout(self._sub_container)
        self._sub_layout.setContentsMargins(0, 0, 0, 0)
        self._sub_layout.setSpacing(6)
        self._sub_layout.addStretch()
        scroll.setWidget(self._sub_container)
        layout.addWidget(scroll, stretch=1)

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

    # ── Subtask rows ──────────────────────────────────────────────────────────

    def _add_subtask_row(self, title: str = "", done: bool = False) -> None:
        row_widget = QWidget()
        row_widget.setStyleSheet("background: transparent;")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        chk = QCheckBox()
        chk.setChecked(done)
        chk.setStyleSheet(f"QCheckBox {{ background: transparent; color: {self._tc()}; }}")
        row.addWidget(chk)

        edit = QLineEdit(title)
        edit.setPlaceholderText("Subtask…")
        edit.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,{'0.08' if self._art_dark else '0.60'});"
            f" border: 1px solid rgba({'255,255,255,0.15' if self._art_dark else '0,0,0,0.12'});"
            f" border-radius: 7px; color: {self._tc()}; font-size: 13px; padding: 5px 10px; }}"
        )
        row.addWidget(edit, stretch=1)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {self._tc()}; font-size: 11px; }}"
            "QPushButton:hover { color: #EF4444; }"
        )
        del_btn.clicked.connect(lambda: self._remove_subtask_row(row_widget, chk, edit))
        row.addWidget(del_btn)

        # Insert before the trailing stretch
        self._sub_layout.insertWidget(self._sub_layout.count() - 1, row_widget)
        self._sub_rows.append((chk, edit))

    def _remove_subtask_row(self, widget: QWidget, chk: QCheckBox, edit: QLineEdit) -> None:
        pair = (chk, edit)
        if pair in self._sub_rows:
            self._sub_rows.remove(pair)
        widget.deleteLater()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        title = self._title_edit.text().strip()
        if not title:
            self._title_edit.setFocus()
            return

        due_date: Optional[datetime] = None
        if self._due_check.isChecked():
            due_date = self._due_edit.dateTime().toPython()

        subtasks = [
            {"title": edit.text().strip(), "done": chk.isChecked()}
            for chk, edit in self._sub_rows
            if edit.text().strip()
        ]
        subs_json = json.dumps(subtasks) if subtasks else None

        if self._task is None:
            task = self._task_service.create_task(
                self._user.id, title, due_date=due_date, subtasks=subtasks or None
            )
        else:
            task = self._task_service.update_task(
                self._task.id,
                title=title,
                due_date=due_date,
                subtasks=subs_json,
                updated_at=datetime.utcnow(),
            )

        self.task_saved.emit(task)
        self.accept()
