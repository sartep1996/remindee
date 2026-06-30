from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QProgressBar,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from remindee.models.task import Task, TaskPriority, TaskStatus
from remindee.services.task_service import compute_progress

# ── Display constants ─────────────────────────────────────────────────────────

_STATUS_ICONS = {
    TaskStatus.NOT_STARTED: "○",
    TaskStatus.IN_PROGRESS:  "◑",
    TaskStatus.BLOCKED:      "⊘",
    TaskStatus.COMPLETED:    "✓",
    TaskStatus.CANCELLED:    "✗",
}

_STATUS_COLORS = {
    TaskStatus.NOT_STARTED: "#888888",
    TaskStatus.IN_PROGRESS:  "#4A9EFF",
    TaskStatus.BLOCKED:      "#FF6B6B",
    TaskStatus.COMPLETED:    "#4CAF50",
    TaskStatus.CANCELLED:    "#777777",
}

_STATUS_LABELS = {
    TaskStatus.NOT_STARTED: "Not Started",
    TaskStatus.IN_PROGRESS:  "In Progress",
    TaskStatus.BLOCKED:      "Blocked",
    TaskStatus.COMPLETED:    "Completed",
    TaskStatus.CANCELLED:    "Cancelled",
}

_PRIORITY_DATA: dict[TaskPriority, tuple[str, str, str]] = {
    TaskPriority.LOW:    ("LOW",    "#999999", "rgba(153,153,153,0.20)"),
    TaskPriority.MEDIUM: ("MED",    "#FFB74D", "rgba(255,183,77,0.22)"),
    TaskPriority.HIGH:   ("HIGH",   "#FF7043", "rgba(255,112,67,0.22)"),
    TaskPriority.URGENT: ("URGENT", "#F44336", "rgba(244,67,54,0.28)"),
}


class TaskCard(QFrame):
    """
    Renders a single task row.  Parent tasks auto-expand to show children.
    All interactions (toggle, edit, delete, add-subtask, set-status) are
    dispatched via a callbacks dict passed from the view layer so signals
    don't have to bubble through arbitrary nesting depth.

    Expected callbacks keys: "toggle", "edit", "delete",
                             "add_subtask", "set_status", "refresh"
    """

    def __init__(
        self,
        task: Task,
        tasks_by_parent: dict,
        task_by_id: dict,
        depth: int = 0,
        callbacks: dict | None = None,
        show_children: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._task           = task
        self._by_parent      = tasks_by_parent
        self._by_id          = task_by_id
        self._depth          = depth
        self._cbs            = callbacks or {}
        self._show_children  = show_children
        self._child_tasks    = tasks_by_parent.get(task.id, [])
        self._expanded       = depth < 2   # auto-open first two levels
        self._children_widget: QWidget | None = None

        self.setObjectName("TaskCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self._depth * 22, 0, 0, 0)
        outer.setSpacing(0)

        # ── Row ───────────────────────────────────────────────────────────────
        row = QFrame()
        row.setObjectName("TaskRow")
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(6, 7, 8, 7)
        row_lay.setSpacing(6)

        # Colored left accent
        status_col = _STATUS_COLORS[self._task.status]
        accent = QFrame()
        accent.setFixedWidth(3)
        accent.setStyleSheet(f"background: {status_col}; border-radius: 2px;")
        row_lay.addWidget(accent)

        # Toggle / status button
        self._toggle_btn = QPushButton()
        self._toggle_btn.setObjectName("TaskToggleBtn")
        self._toggle_btn.setFixedSize(26, 26)
        if self._child_tasks and self._show_children:
            self._toggle_btn.setText("▼" if self._expanded else "▶")
            self._toggle_btn.clicked.connect(self._on_expand)
        else:
            self._toggle_btn.setText(_STATUS_ICONS[self._task.status])
            self._toggle_btn.setStyleSheet(f"color: {status_col}; font-weight: 700;")
            self._toggle_btn.clicked.connect(self._on_toggle_status)
        row_lay.addWidget(self._toggle_btn)

        # Title + optional progress column
        mid = QVBoxLayout()
        mid.setSpacing(3)

        self._title_lbl = QLabel(self._task.title)
        self._title_lbl.setObjectName("TaskTitle")
        if self._task.status == TaskStatus.COMPLETED:
            self._title_lbl.setStyleSheet(
                "color: rgba(255,255,255,0.38); text-decoration: line-through;"
            )
        elif self._task.status == TaskStatus.CANCELLED:
            self._title_lbl.setStyleSheet("color: rgba(255,255,255,0.30);")
        mid.addWidget(self._title_lbl)

        if self._child_tasks:
            done, total = compute_progress(self._task.id, self._by_parent, self._by_id)
            if total > 0:
                prog_row = QHBoxLayout()
                prog_row.setSpacing(6)
                prog_row.setContentsMargins(0, 0, 0, 0)

                pbar = QProgressBar()
                pbar.setObjectName("TaskProgress")
                pbar.setRange(0, total)
                pbar.setValue(done)
                pbar.setFixedHeight(4)
                pbar.setTextVisible(False)
                prog_row.addWidget(pbar, stretch=1)

                pct = int(done / total * 100)
                prog_lbl = QLabel(f"{done}/{total}  ·  {pct}%")
                prog_lbl.setObjectName("TaskProgressLabel")
                prog_row.addWidget(prog_lbl)

                mid.addLayout(prog_row)

        row_lay.addLayout(mid, stretch=1)

        # Priority badge
        p_text, p_fg, p_bg = _PRIORITY_DATA[self._task.priority]
        prio_lbl = QLabel(p_text)
        prio_lbl.setObjectName("TaskPriorityBadge")
        prio_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prio_lbl.setFixedWidth(50)
        prio_lbl.setStyleSheet(
            f"color:{p_fg}; background:{p_bg}; border-radius:4px;"
            f" padding:2px 4px; font-size:10px; font-weight:700;"
        )
        row_lay.addWidget(prio_lbl)

        # Due date
        if self._task.due_date:
            dt = self._task.due_date
            today = date.today()
            is_done = self._task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
            if not is_done and dt.date() < today:
                due_text  = f"⚠ {dt.strftime('%b %d')}"
                due_color = "#FF6B6B"
            elif dt.date() == today and not is_done:
                due_text  = "Today"
                due_color = "#FFB74D"
            else:
                due_text  = dt.strftime("%b %d")
                due_color = "rgba(255,255,255,0.46)"
            due_lbl = QLabel(due_text)
            due_lbl.setObjectName("TaskDueLabel")
            due_lbl.setStyleSheet(f"color:{due_color}; font-size:11px; min-width:48px;")
            row_lay.addWidget(due_lbl)

        # More (⋮) menu
        more_btn = QPushButton("⋮")
        more_btn.setObjectName("TaskMoreBtn")
        more_btn.setFixedSize(26, 26)
        more_btn.clicked.connect(self._show_menu)
        row_lay.addWidget(more_btn)

        outer.addWidget(row)

        # ── Children ──────────────────────────────────────────────────────────
        if self._child_tasks and self._show_children:
            self._children_widget = QWidget()
            self._children_widget.setObjectName("TaskChildBox")
            kids_lay = QVBoxLayout(self._children_widget)
            kids_lay.setContentsMargins(0, 3, 0, 0)
            kids_lay.setSpacing(3)

            for child in self._child_tasks:
                card = TaskCard(
                    child,
                    self._by_parent,
                    self._by_id,
                    depth=self._depth + 1,
                    callbacks=self._cbs,
                    show_children=True,
                )
                kids_lay.addWidget(card)

            self._children_widget.setVisible(self._expanded)
            outer.addWidget(self._children_widget)

    # ── Interaction ───────────────────────────────────────────────────────────

    def _on_expand(self) -> None:
        self._expanded = not self._expanded
        self._toggle_btn.setText("▼" if self._expanded else "▶")
        if self._children_widget:
            self._children_widget.setVisible(self._expanded)

    def _on_toggle_status(self) -> None:
        cb = self._cbs.get("toggle")
        if cb:
            cb(self._task.id)

    def mouseDoubleClickEvent(self, event) -> None:
        cb = self._cbs.get("edit")
        if cb:
            cb(self._task.id)

    def _show_menu(self) -> None:
        menu = QMenu(self)

        # Status submenu
        status_menu = menu.addMenu("Set Status")
        for s in TaskStatus:
            act = status_menu.addAction(_STATUS_LABELS[s])
            act.triggered.connect(
                lambda checked=False, st=s: (
                    self._cbs.get("set_status", lambda *_: None)(self._task.id, st)
                )
            )

        menu.addSeparator()

        sub_act = menu.addAction("Add Subtask")
        sub_act.triggered.connect(
            lambda: self._cbs.get("add_subtask", lambda *_: None)(self._task.id)
        )

        edit_act = menu.addAction("Edit Task")
        edit_act.triggered.connect(
            lambda: self._cbs.get("edit", lambda *_: None)(self._task.id)
        )

        menu.addSeparator()

        del_act = menu.addAction("Delete Task")
        del_act.triggered.connect(
            lambda: self._cbs.get("delete", lambda *_: None)(self._task.id)
        )

        menu.exec(QCursor.pos())
