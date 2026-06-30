from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from remindee.models.task import Task, TaskPriority, TaskStatus
from remindee.models.user import User
from remindee.services.task_service import TaskService

_STATUS_LABELS = [
    ("Not Started", TaskStatus.NOT_STARTED),
    ("In Progress",  TaskStatus.IN_PROGRESS),
    ("Blocked",      TaskStatus.BLOCKED),
    ("Completed",    TaskStatus.COMPLETED),
    ("Cancelled",    TaskStatus.CANCELLED),
]

_PRIORITY_LABELS = [
    ("Low",    TaskPriority.LOW),
    ("Medium", TaskPriority.MEDIUM),
    ("High",   TaskPriority.HIGH),
    ("Urgent", TaskPriority.URGENT),
]

_PRIORITY_COLORS = {
    TaskPriority.LOW:    ("#999", "rgba(153,153,153,0.18)"),
    TaskPriority.MEDIUM: ("#FFB74D", "rgba(255,183,77,0.18)"),
    TaskPriority.HIGH:   ("#FF7043", "rgba(255,112,67,0.18)"),
    TaskPriority.URGENT: ("#F44336", "rgba(244,67,54,0.22)"),
}


class TaskDialog(QDialog):
    """Create or edit a task, with inline subtask management when editing."""

    task_saved = Signal(object)  # Task

    def __init__(
        self,
        user: User,
        task_service: TaskService,
        task: Optional[Task] = None,
        parent_task_id: Optional[int] = None,
        children: Optional[list[Task]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._user         = user
        self._svc          = task_service
        self._task         = task          # None = new task
        self._parent_id    = parent_task_id
        self._children     = children or []
        self._priority     = (task.priority if task else TaskPriority.MEDIUM)
        self._subtasks_pending: list[str] = []   # titles to create on save
        self._subtasks_delete: list[int]  = []   # child IDs to delete on save

        self.setModal(True)
        self.setWindowTitle("Edit Task" if task else "New Task")
        self.setMinimumWidth(480)
        self.resize(520, 560 if (task and children) else 420)

        self._build()
        self._populate()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(14)

        # Title
        self._title_edit = QLineEdit()
        self._title_edit.setObjectName("TaskTitleInput")
        self._title_edit.setPlaceholderText("Task name…")
        root.addWidget(self._title_edit)

        # Description
        self._desc_edit = QTextEdit()
        self._desc_edit.setObjectName("TaskDescEdit")
        self._desc_edit.setPlaceholderText("Description (optional)…")
        self._desc_edit.setFixedHeight(72)
        root.addWidget(self._desc_edit)

        # ── Priority row ──────────────────────────────────────────────────────
        prio_row = QHBoxLayout()
        prio_row.setSpacing(6)
        prio_lbl = QLabel("Priority:")
        prio_lbl.setObjectName("DialogFieldLabel")
        prio_row.addWidget(prio_lbl)

        self._prio_btns: dict[TaskPriority, QPushButton] = {}
        for label, prio in _PRIORITY_LABELS:
            btn = QPushButton(label)
            btn.setObjectName("TaskPrioBtn")
            btn.setCheckable(True)
            fg, bg = _PRIORITY_COLORS[prio]
            btn.setProperty("prio_fg", fg)
            btn.setProperty("prio_bg", bg)
            btn.clicked.connect(lambda checked, p=prio: self._set_priority(p))
            self._prio_btns[prio] = btn
            prio_row.addWidget(btn)

        prio_row.addStretch()
        root.addLayout(prio_row)
        self._set_priority(self._priority)

        # ── Status + due date row ─────────────────────────────────────────────
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)

        status_lbl = QLabel("Status:")
        status_lbl.setObjectName("DialogFieldLabel")
        meta_row.addWidget(status_lbl)

        self._status_combo = QComboBox()
        self._status_combo.setObjectName("TaskStatusCombo")
        for label, st in _STATUS_LABELS:
            self._status_combo.addItem(label, st)
        meta_row.addWidget(self._status_combo)

        meta_row.addStretch()

        self._due_toggle = QPushButton("+ Set due date")
        self._due_toggle.setObjectName("TaskDueToggle")
        self._due_toggle.setCheckable(True)
        self._due_toggle.clicked.connect(self._on_due_toggle)
        meta_row.addWidget(self._due_toggle)

        root.addLayout(meta_row)

        # Due date widget (hidden by default)
        self._due_edit = QDateEdit()
        self._due_edit.setObjectName("TaskDueEdit")
        self._due_edit.setCalendarPopup(True)
        self._due_edit.setDate(QDate.currentDate().addDays(1))
        self._due_edit.setDisplayFormat("MMM d, yyyy")
        self._due_edit.setVisible(False)
        root.addWidget(self._due_edit)

        # ── Subtasks section (shown when editing a task) ──────────────────────
        if self._task:
            sub_sep = QFrame()
            sub_sep.setFrameShape(QFrame.Shape.HLine)
            sub_sep.setStyleSheet("color: rgba(255,255,255,0.15);")
            root.addWidget(sub_sep)

            sub_hdr = QHBoxLayout()
            sub_lbl = QLabel("Subtasks")
            sub_lbl.setObjectName("DialogSectionLabel")
            sub_hdr.addWidget(sub_lbl, stretch=1)
            root.addLayout(sub_hdr)

            # Subtask list
            self._sub_list = QVBoxLayout()
            self._sub_list.setSpacing(4)
            sub_scroll_content = QWidget()
            sub_scroll_content.setLayout(self._sub_list)
            sub_scroll = QScrollArea()
            sub_scroll.setWidgetResizable(True)
            sub_scroll.setMaximumHeight(160)
            sub_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            sub_scroll.setWidget(sub_scroll_content)
            root.addWidget(sub_scroll)

            for child in self._children:
                self._add_subtask_row(child.title, child.id, child.status)

            # Quick-add subtask
            add_row = QHBoxLayout()
            add_row.setSpacing(6)
            self._sub_input = QLineEdit()
            self._sub_input.setObjectName("SubtaskInput")
            self._sub_input.setPlaceholderText("Add subtask…")
            self._sub_input.returnPressed.connect(self._on_add_subtask_entered)
            add_row.addWidget(self._sub_input)
            add_sub_btn = QPushButton("Add")
            add_sub_btn.setObjectName("SecondaryBtn")
            add_sub_btn.clicked.connect(self._on_add_subtask_entered)
            add_row.addWidget(add_sub_btn)
            root.addLayout(add_row)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _add_subtask_row(
        self, title: str, task_id: Optional[int] = None, status: TaskStatus = TaskStatus.NOT_STARTED
    ) -> None:
        row_widget = QWidget()
        row_lay = QHBoxLayout(row_widget)
        row_lay.setContentsMargins(0, 2, 0, 2)
        row_lay.setSpacing(6)

        done_lbl = QLabel("✓" if status == TaskStatus.COMPLETED else "○")
        done_lbl.setFixedWidth(16)
        row_lay.addWidget(done_lbl)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("SubtaskRowTitle")
        if status == TaskStatus.COMPLETED:
            title_lbl.setStyleSheet(
                "color: rgba(255,255,255,0.38); text-decoration: line-through;"
            )
        row_lay.addWidget(title_lbl, stretch=1)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("SubtaskDeleteBtn")
        del_btn.setFixedSize(22, 22)

        if task_id is not None:
            del_btn.clicked.connect(
                lambda checked=False, tid=task_id, w=row_widget: self._on_delete_existing(tid, w)
            )
        else:
            del_btn.clicked.connect(
                lambda checked=False, t=title, w=row_widget: self._on_delete_pending(t, w)
            )
        row_lay.addWidget(del_btn)

        self._sub_list.addWidget(row_widget)

    # ── Populate (edit mode) ──────────────────────────────────────────────────

    def _populate(self) -> None:
        if not self._task:
            return
        self._title_edit.setText(self._task.title or "")
        self._desc_edit.setPlainText(self._task.description or "")
        self._set_priority(self._task.priority)

        for i, (_, st) in enumerate(_STATUS_LABELS):
            if st == self._task.status:
                self._status_combo.setCurrentIndex(i)
                break

        if self._task.due_date:
            self._due_toggle.setChecked(True)
            self._due_toggle.setText("Due date ✓")
            self._due_edit.setVisible(True)
            dt = self._task.due_date
            self._due_edit.setDate(QDate(dt.year, dt.month, dt.day))

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _set_priority(self, prio: TaskPriority) -> None:
        self._priority = prio
        for p, btn in self._prio_btns.items():
            active = p == prio
            btn.setChecked(active)
            fg, bg = _PRIORITY_COLORS[p]
            if active:
                btn.setStyleSheet(
                    f"background:{bg}; color:{fg}; border:1px solid {fg};"
                    f" border-radius:6px; padding:4px 10px; font-weight:700;"
                )
            else:
                btn.setStyleSheet(
                    "background:transparent; color:rgba(255,255,255,0.50);"
                    " border:1px solid rgba(255,255,255,0.18);"
                    " border-radius:6px; padding:4px 10px;"
                )

    def _on_due_toggle(self, checked: bool) -> None:
        self._due_edit.setVisible(checked)
        self._due_toggle.setText("Due date ✓" if checked else "+ Set due date")

    def _on_add_subtask_entered(self) -> None:
        title = self._sub_input.text().strip()
        if not title:
            return
        self._subtasks_pending.append(title)
        self._add_subtask_row(title, task_id=None)
        self._sub_input.clear()

    def _on_delete_existing(self, task_id: int, widget: QWidget) -> None:
        self._subtasks_delete.append(task_id)
        widget.hide()

    def _on_delete_pending(self, title: str, widget: QWidget) -> None:
        if title in self._subtasks_pending:
            self._subtasks_pending.remove(title)
        widget.hide()

    def _save(self) -> None:
        title = self._title_edit.text().strip()
        if not title:
            self._title_edit.setPlaceholderText("Please enter a task name!")
            return

        desc    = self._desc_edit.toPlainText().strip() or None
        status  = self._status_combo.currentData()
        due_dt  = None
        if self._due_toggle.isChecked():
            qd     = self._due_edit.date()
            due_dt = datetime(qd.year(), qd.month(), qd.day())

        if self._task:
            # Update existing task
            kwargs: dict = dict(
                title=title,
                description=desc,
                priority=self._priority,
                status=status,
                due_date=due_dt,
            )
            if status == TaskStatus.COMPLETED and not self._task.completion_date:
                kwargs["completion_date"] = datetime.utcnow()
            elif status != TaskStatus.COMPLETED:
                kwargs["completion_date"] = None
            saved = self._svc.update_task(self._task.id, **kwargs)

            # Apply subtask mutations
            for tid in self._subtasks_delete:
                try:
                    self._svc.delete_task(tid)
                except Exception:
                    pass
            for sub_title in self._subtasks_pending:
                self._svc.create_task(
                    user_id=self._user.id,
                    title=sub_title,
                    parent_id=self._task.id,
                )
        else:
            saved = self._svc.create_task(
                user_id=self._user.id,
                title=title,
                parent_id=self._parent_id,
                description=desc,
                priority=self._priority,
                status=status,
                due_date=due_dt,
            )

        self.task_saved.emit(saved)
        self.accept()
