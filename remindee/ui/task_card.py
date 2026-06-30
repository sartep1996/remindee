from __future__ import annotations

import random
from datetime import datetime

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QPushButton, QSizePolicy, QVBoxLayout,
)

from remindee.models.task import Task
from remindee.services.task_service import TaskService
from remindee.ui.reminder_card import (
    _DARK_BASES, _DARK_BTN, _SCHEMES, _STYLES,
    _OutlinedLabel, _draw_base, _draw_grain,
)


class TaskCard(QFrame):
    edit_requested    = Signal(object)      # Task
    delete_requested  = Signal(object)      # Task
    subtask_toggled   = Signal(int, int, bool)  # task_id, subtask_idx, done

    def __init__(self, task: Task, parent=None) -> None:
        super().__init__(parent)
        self._task    = task
        self._hovered = False
        self._subs    = TaskService.parse_subtasks(task)

        self._seed    = (task.id or abs(hash(task.title))) & 0x7FFFFFFF
        self._is_dark = (self._seed * 11 + 5) % 5 == 0

        self.setObjectName("TaskCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumHeight(72)
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 10)
        outer.setSpacing(6)

        # ── Top row: title + buttons ──────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)

        title = _OutlinedLabel(self._task.title)
        title.setObjectName("CardTitle")
        title.setFont(QFont("Marker Felt", 14))
        top.addWidget(title, stretch=1)

        edit_btn = QPushButton("✏")
        edit_btn.setObjectName("CardActionBtn")
        edit_btn.setFixedSize(38, 38)
        edit_btn.setToolTip("Edit task")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._task))
        top.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("CardActionBtn")
        del_btn.setFixedSize(38, 38)
        del_btn.setToolTip("Delete task")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._task))
        top.addWidget(del_btn)

        outer.addLayout(top)

        if self._is_dark:
            for btn in (edit_btn, del_btn):
                btn.setStyleSheet(_DARK_BTN)

        # ── Due date ──────────────────────────────────────────────────────────
        if self._task.due_date:
            due_lbl = _OutlinedLabel(self._format_due())
            due_lbl.setObjectName("CardTrigger")
            outer.addWidget(due_lbl)

        # ── Progress bar + label ──────────────────────────────────────────────
        done, total = TaskService.progress(self._task)
        if total > 0:
            pct = int(done / total * 100)

            prog_row = QHBoxLayout()
            prog_row.setSpacing(8)
            prog_row.setContentsMargins(0, 2, 0, 0)

            self._prog_bar = _ProgressBar(done, total, self._is_dark)
            prog_row.addWidget(self._prog_bar, stretch=1)

            prog_lbl = _OutlinedLabel(f"{done}/{total}  ·  {pct}%")
            prog_lbl.setObjectName("CardTrigger")
            prog_row.addWidget(prog_lbl)

            outer.addLayout(prog_row)

        # ── Subtask list ──────────────────────────────────────────────────────
        if self._subs:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("background: rgba(0,0,0,0.08); max-height: 1px; margin: 2px 0;")
            outer.addWidget(sep)

            for idx, sub in enumerate(self._subs):
                row = QHBoxLayout()
                row.setSpacing(8)
                row.setContentsMargins(0, 1, 0, 1)

                chk = QPushButton("☑" if sub.get("done") else "☐")
                chk.setObjectName("TaskCheckBtn")
                chk.setFixedSize(26, 26)
                if self._is_dark:
                    chk.setStyleSheet(_DARK_BTN)
                chk.clicked.connect(
                    lambda checked=False, i=idx, d=sub.get("done"): (
                        self.subtask_toggled.emit(self._task.id, i, not d)
                    )
                )
                row.addWidget(chk)

                sub_lbl = _OutlinedLabel(sub.get("title", ""))
                sub_lbl.setObjectName("SubtaskLabel")
                if sub.get("done"):
                    sub_lbl.setStyleSheet(
                        "color: rgba(80,80,80,0.55); text-decoration: line-through;"
                        if not self._is_dark else
                        "color: rgba(200,200,200,0.40); text-decoration: line-through;"
                    )
                row.addWidget(sub_lbl, stretch=1)
                outer.addLayout(row)

    def _format_due(self) -> str:
        dt = self._task.due_date
        today = datetime.utcnow().date()
        if dt.date() < today:
            return f"⚠ Overdue · {dt.strftime('%b %d')}"
        if dt.date() == today:
            return "Due today"
        return f"Due {dt.strftime('%b %d, %Y')}"

    # ── Events ────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        self.edit_requested.emit(self._task)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    # ── Painting ─────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r      = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = 14.0

        clip = QPainterPath()
        clip.addRoundedRect(r, radius, radius)
        p.setClipPath(clip)

        if self._is_dark:
            p.fillRect(self.rect(), _DARK_BASES[self._seed % len(_DARK_BASES)])
        else:
            p.fillRect(self.rect(), QColor(255, 255, 255))

        rng     = random.Random(self._seed)
        palette = _SCHEMES[self._seed % len(_SCHEMES)]
        style   = (self._seed * 17 + 5) % len(_STYLES)

        if not self._is_dark:
            _draw_base(p, r, rng, palette, self._seed)
        _STYLES[style](p, r, rng, palette)
        if (self._seed * 3 + 1) % 5 < 2:
            _draw_grain(p, r, rng)

        veil = QColor(0, 0, 0, 55) if self._is_dark else QColor(255, 255, 255, 72)
        p.fillPath(clip, veil)

        p.setClipping(False)
        alpha = 220 if self._hovered else (110 if self._is_dark else 70)
        col   = QColor(255, 145, 90, alpha) if self._is_dark else QColor(255, 107, 53, alpha)
        p.setPen(QPen(col, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, radius, radius)

    def refresh(self, task: Task) -> None:
        self._task    = task
        self._subs    = TaskService.parse_subtasks(task)
        self._seed    = (task.id or abs(hash(task.title))) & 0x7FFFFFFF
        self._is_dark = (self._seed * 11 + 5) % 5 == 0
        old = self.layout()
        if old:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            old.deleteLater()
        self._build()
        self.update()


class _ProgressBar(QFrame):
    """Thin painted progress bar matching the card art palette."""

    def __init__(self, done: int, total: int, dark: bool, parent=None) -> None:
        super().__init__(parent)
        self._done  = done
        self._total = total
        self._dark  = dark
        self.setFixedHeight(6)
        self.setMinimumWidth(60)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        # Track
        track = QColor(0, 0, 0, 30) if not self._dark else QColor(255, 255, 255, 25)
        p.setBrush(track)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 3, 3)

        # Fill
        if self._total > 0:
            ratio = self._done / self._total
            fill_rect = QRectF(r.x(), r.y(), r.width() * ratio, r.height())
            p.setBrush(QColor(255, 107, 53, 210))
            p.drawRoundedRect(fill_rect, 3, 3)
