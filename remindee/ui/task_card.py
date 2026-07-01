from __future__ import annotations

import random
from datetime import datetime
from typing import Optional

from PySide6.QtCore import (
    Property, QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, Signal,
)
from PySide6.QtGui import QColor, QDrag, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLineEdit, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import QMimeData

from remindee.models.task import Task
from remindee.services.task_service import TaskService

_TASK_MIME = "application/x-remindee-task-id"
from remindee.ui.reminder_card import (
    _DARK_BASES, _DARK_BTN, _SCHEMES, _STYLES,
    _OutlinedLabel, _draw_base, _draw_grain,
)


# ── Animated circle checkbox ──────────────────────────────────────────────────

class _AnimCheck(QPushButton):
    """Animated circle checkbox with orange fill and check-mark."""

    def __init__(self, size: int = 24, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._fill_val: float = 0.0
        self.setFixedSize(size, size)
        self.setStyleSheet(
            "QPushButton { background: transparent; border: none; padding: 0; }"
        )

        self._anim = QPropertyAnimation(self, b"_fill_prop")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)

    # PySide6 Property declaration
    def _get_fill(self) -> float:
        return self._fill_val

    def _set_fill(self, val: float) -> None:
        self._fill_val = max(0.0, min(1.0, val))
        self.update()

    _fill_prop = Property(float, _get_fill, _set_fill)

    def set_checked(self, val: bool, animate: bool = True) -> None:
        target = 1.0 if val else 0.0
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._fill_val)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._fill_val = target
            self.update()

    def is_checked(self) -> bool:
        return self._fill_val > 0.5

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        f = self._fill_val
        r = self._size / 2 - 2.0
        cx = self._size / 2.0
        cy = self._size / 2.0

        # Border
        border_alpha = int(80 + f * 175)
        p.setPen(QPen(QColor(255, 107, 53, border_alpha), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Fill
        if f > 0.001:
            fill_col = QColor(255, 107, 53, int(f * 220))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill_col)
            p.drawEllipse(QPointF(cx, cy), r - 0.5, r - 0.5)

        # Checkmark (fades in after fill > 0.15)
        if f > 0.15:
            alpha = int(min(255, (f - 0.15) / 0.85 * 255))
            pen = QPen(QColor(255, 255, 255, alpha), 2.0, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            # Knee point: left → knee → top-right
            kx = cx - r * 0.1
            ky = cy + r * 0.2
            p.drawLine(
                QPointF(cx - r * 0.45, cy),
                QPointF(kx, ky),
            )
            p.drawLine(
                QPointF(kx, ky),
                QPointF(cx + r * 0.45, cy - r * 0.45),
            )

        p.end()


# ── Subtask row ───────────────────────────────────────────────────────────────

class _SubtaskRow(QWidget):
    toggled = Signal(int, bool)  # (idx, new_done)

    def __init__(
        self,
        idx: int,
        title: str,
        done: bool,
        is_dark: bool,
        is_last: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._idx = idx
        self._is_dark = is_dark
        self._is_last = is_last

        layout = QHBoxLayout(self)
        layout.setContentsMargins(26, 1, 0, 1)
        layout.setSpacing(6)

        self._chk = _AnimCheck(size=20)
        self._chk.set_checked(done, animate=False)
        self._chk.clicked.connect(self._on_click)
        layout.addWidget(self._chk)

        self._lbl = _OutlinedLabel(title)
        self._lbl.setObjectName("SubtaskLabel")
        self._apply_label_style(done)
        layout.addWidget(self._lbl, stretch=1)

    def _apply_label_style(self, done: bool) -> None:
        if done:
            color = "rgba(200,200,200,0.40)" if self._is_dark else "rgba(80,80,80,0.55)"
            self._lbl.setStyleSheet(
                f"color: {color}; text-decoration: line-through;"
            )
        else:
            self._lbl.setStyleSheet("")

    def _on_click(self) -> None:
        new_done = not self._chk.is_checked()
        self._chk.set_checked(new_done)
        self._apply_label_style(new_done)
        self.toggled.emit(self._idx, new_done)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        line_col = (
            QColor(255, 255, 255, 40) if self._is_dark else QColor(60, 26, 0, 28)
        )
        p.setPen(QPen(line_col, 1.0))

        x = 12
        mid_y = self.height() // 2
        # Vertical segment: top → mid (or top → bottom if not last)
        bottom_y = mid_y if self._is_last else self.height()
        p.drawLine(x, 0, x, bottom_y)
        # Horizontal stub
        p.drawLine(x, mid_y, 22, mid_y)

        p.end()
        super().paintEvent(event)


# ── Quick-add inline row ──────────────────────────────────────────────────────

class _QuickAdd(QWidget):
    submitted = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(26, 2, 0, 2)
        layout.setSpacing(4)

        self._add_btn = QPushButton("+ Add subtask")
        self._add_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " color: #FF6B35; font-size: 12px; text-align: left; padding: 0; }"
            "QPushButton:hover { color: #E85A25; }"
        )
        self._add_btn.clicked.connect(self._expand)
        layout.addWidget(self._add_btn, stretch=1)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText("Subtask name…")
        self._edit.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,0.60);"
            " border: 1px solid rgba(255,107,53,0.35);"
            " border-radius: 6px; font-size: 12px; padding: 3px 8px; }"
        )
        self._edit.hide()
        self._edit.returnPressed.connect(self._submit)
        layout.addWidget(self._edit, stretch=1)

        self._cancel_btn = QPushButton("✕")
        self._cancel_btn.setFixedSize(20, 20)
        self._cancel_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " color: rgba(100,60,30,0.60); font-size: 11px; }"
        )
        self._cancel_btn.hide()
        self._cancel_btn.clicked.connect(self._collapse)
        layout.addWidget(self._cancel_btn)

    def _expand(self) -> None:
        self._add_btn.hide()
        self._edit.show()
        self._cancel_btn.show()
        self._edit.setFocus()
        self._edit.clear()

    def _collapse(self) -> None:
        self._edit.hide()
        self._cancel_btn.hide()
        self._add_btn.show()

    def _submit(self) -> None:
        text = self._edit.text().strip()
        if text:
            self.submitted.emit(text)
        self._collapse()


# ── Mini progress bar (animated) ──────────────────────────────────────────────

class _MiniProgress(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._display_val: float = 0.0
        self._done: int = 0
        self._total: int = 0
        self.setFixedHeight(6)
        self.setMinimumWidth(60)

        self._anim = QPropertyAnimation(self, b"_display_prop")
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_display(self) -> float:
        return self._display_val

    def _set_display(self, val: float) -> None:
        self._display_val = max(0.0, min(1.0, val))
        self.update()

    _display_prop = Property(float, _get_display, _set_display)

    def animate_to(self, done: int, total: int) -> None:
        self._done = done
        self._total = total
        target = (done / total) if total > 0 else 0.0
        self._anim.stop()
        self._anim.setStartValue(self._display_val)
        self._anim.setEndValue(target)
        self._anim.start()

    def _bar_color(self) -> QColor:
        if self._total == 0:
            return QColor(255, 107, 53)
        ratio = self._done / self._total
        if ratio >= 1.0:
            return QColor(34, 197, 94)    # green
        if ratio >= 0.6:
            return QColor(251, 146, 60)   # amber
        return QColor(255, 107, 53)       # orange

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        # Track
        p.setBrush(QColor(0, 0, 0, 30))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 3, 3)

        # Fill
        if self._display_val > 0.0:
            fill_rect = QRectF(r.x(), r.y(), r.width() * self._display_val, r.height())
            p.setBrush(self._bar_color())
            p.drawRoundedRect(fill_rect, 3, 3)

        p.end()


# ── Main card ─────────────────────────────────────────────────────────────────

class TaskCard(QFrame):
    edit_requested   = Signal(object)          # Task
    delete_requested = Signal(object)          # Task
    done_toggled     = Signal(int, bool)       # task_id, is_done
    subtask_toggled  = Signal(int, int, bool)  # task_id, subtask_idx, done
    subtask_added    = Signal(int, str)        # task_id, title

    # Class-level set to persist collapse state across refreshes
    _collapsed_ids: set = set()

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
        outer.setSpacing(4)

        # ── Header row ───────────────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(6)

        self._done_chk = _AnimCheck(size=26)
        self._done_chk.set_checked(self._task.is_done, animate=False)
        self._done_chk.clicked.connect(self._on_done_click)
        top.addWidget(self._done_chk)

        title_text = self._task.title
        title = _OutlinedLabel(title_text)
        title.setObjectName("CardTitle")
        title.setFont(QFont("Marker Felt", 13))
        if self._task.is_done:
            title.setStyleSheet(
                "color: rgba(80,80,80,0.50); text-decoration: line-through;"
                if not self._is_dark else
                "color: rgba(200,200,200,0.35); text-decoration: line-through;"
            )
        top.addWidget(title, stretch=1)

        # Collapse button (only if subtasks exist)
        self._col_btn_ref: Optional[QPushButton] = None
        if self._subs:
            collapsed = self._task.id in TaskCard._collapsed_ids
            col_btn = QPushButton("▸" if collapsed else "▾")
            col_btn.setFixedSize(24, 24)
            if self._is_dark:
                col_btn.setStyleSheet(
                    "QPushButton { background: transparent; border: none;"
                    " color: rgba(225,205,185,0.70); font-size: 11px; }"
                    "QPushButton:hover { color: #FF9560; }"
                )
            else:
                col_btn.setStyleSheet(
                    "QPushButton { background: transparent; border: none;"
                    " color: rgba(100,60,30,0.70); font-size: 11px; }"
                    "QPushButton:hover { color: #FF6B35; }"
                )
            col_btn.clicked.connect(self._toggle_collapse)
            top.addWidget(col_btn)
            self._col_btn_ref = col_btn

        edit_btn = QPushButton("✏")
        edit_btn.setObjectName("CardActionBtn")
        edit_btn.setFixedSize(32, 32)
        edit_btn.setToolTip("Edit task")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self._task))
        top.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setObjectName("CardActionBtn")
        del_btn.setFixedSize(32, 32)
        del_btn.setToolTip("Delete task")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._task))
        top.addWidget(del_btn)

        outer.addLayout(top)

        if self._is_dark:
            for btn in (edit_btn, del_btn):
                btn.setStyleSheet(_DARK_BTN)

        # ── Due date badge ────────────────────────────────────────────────────
        if self._task.due_date:
            due_lbl = _OutlinedLabel(self._format_due())
            due_lbl.setObjectName("CardTrigger")
            color_style = self._due_color_style()
            if color_style:
                due_lbl.setStyleSheet(color_style)
            due_row = QHBoxLayout()
            due_row.setContentsMargins(34, 0, 0, 0)
            due_row.addWidget(due_lbl)
            due_row.addStretch()
            outer.addLayout(due_row)

        # ── Progress row ──────────────────────────────────────────────────────
        done_count, total = TaskService.progress(self._task)
        if total > 0:
            pct = int(done_count / total * 100)

            prog_row = QHBoxLayout()
            prog_row.setContentsMargins(34, 2, 0, 0)
            prog_row.setSpacing(8)

            self._prog_bar = _MiniProgress()
            self._prog_bar.animate_to(done_count, total)
            prog_row.addWidget(self._prog_bar, stretch=1)

            prog_lbl = _OutlinedLabel(f"{done_count}/{total}  ·  {pct}%")
            prog_lbl.setObjectName("CardTrigger")
            prog_row.addWidget(prog_lbl)

            outer.addLayout(prog_row)

        # ── Subtasks section (collapsible) ────────────────────────────────────
        if self._subs:
            collapsed = self._task.id in TaskCard._collapsed_ids

            self._subs_widget = QWidget()
            subs_layout = QVBoxLayout(self._subs_widget)
            subs_layout.setContentsMargins(0, 2, 0, 2)
            subs_layout.setSpacing(0)

            for idx, sub in enumerate(self._subs):
                is_last = (idx == len(self._subs) - 1)
                row = _SubtaskRow(
                    idx=idx,
                    title=sub.get("title", ""),
                    done=sub.get("done", False),
                    is_dark=self._is_dark,
                    is_last=is_last,
                )
                row.toggled.connect(
                    lambda i, d, tid=self._task.id: self.subtask_toggled.emit(tid, i, d)
                )
                subs_layout.addWidget(row)

            # QuickAdd inside subs_widget
            qa = _QuickAdd()
            qa.submitted.connect(
                lambda text, tid=self._task.id: self.subtask_added.emit(tid, text)
            )
            subs_layout.addWidget(qa)

            outer.addWidget(self._subs_widget)

            # Collapse animation setup
            self._col_anim = QPropertyAnimation(self._subs_widget, b"maximumHeight")
            self._col_anim.setDuration(220)
            self._col_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

            if collapsed:
                self._subs_widget.setMaximumHeight(0)
                self._subs_widget.hide()
        else:
            # No subtasks — show QuickAdd directly (not inside subs_widget)
            qa = _QuickAdd()
            qa.submitted.connect(
                lambda text, tid=self._task.id: self.subtask_added.emit(tid, text)
            )
            outer.addWidget(qa)

    def _format_due(self) -> str:
        dt = self._task.due_date
        today = datetime.utcnow().date()
        if dt.date() < today:
            delta = (today - dt.date()).days
            return f"⚠ Overdue {delta}d"
        if dt.date() == today:
            return f"\U0001f534 Due today {dt.strftime('%H:%M')}"
        delta = (dt.date() - today).days
        if delta == 1:
            return f"\U0001f7e1 Tomorrow {dt.strftime('%H:%M')}"
        if delta <= 2:
            return f"\U0001f7e1 {dt.strftime('%a %b %d')} {dt.strftime('%H:%M')}"
        return f"\U0001f4c5 {dt.strftime('%a %b %d')}"

    def _due_color_style(self) -> str:
        dt = self._task.due_date
        today = datetime.utcnow().date()
        if dt.date() < today:
            return "color: #FF3B30;"
        if dt.date() == today:
            return "color: #FF6B35;"
        delta = (dt.date() - today).days
        if delta <= 2:
            return "color: #FF9500;"
        return ""

    # ── Collapse toggle ───────────────────────────────────────────────────────

    def _toggle_collapse(self) -> None:
        if not self._subs:
            return
        task_id = self._task.id
        currently_collapsed = task_id in TaskCard._collapsed_ids

        if currently_collapsed:
            # Expand
            TaskCard._collapsed_ids.discard(task_id)
            self._subs_widget.show()
            self._col_anim.stop()
            self._col_anim.setStartValue(0)
            self._col_anim.setEndValue(2000)
            self._col_anim.start()
            if self._col_btn_ref:
                self._col_btn_ref.setText("▾")
        else:
            # Collapse
            TaskCard._collapsed_ids.add(task_id)
            self._col_anim.stop()
            self._col_anim.setStartValue(self._subs_widget.height())
            self._col_anim.setEndValue(0)
            self._col_anim.start()
            # Hide after animation completes
            self._col_anim.finished.connect(self._hide_subs_after_collapse)
            if self._col_btn_ref:
                self._col_btn_ref.setText("▸")

    def _hide_subs_after_collapse(self) -> None:
        if self._task.id in TaskCard._collapsed_ids and hasattr(self, "_subs_widget"):
            self._subs_widget.hide()
        # Disconnect to avoid repeated calls
        try:
            self._col_anim.finished.disconnect(self._hide_subs_after_collapse)
        except Exception:
            pass

    # ── Done click ────────────────────────────────────────────────────────────

    def _on_done_click(self) -> None:
        new_done = not self._task.is_done
        self._done_chk.set_checked(new_done)
        self.done_toggled.emit(self._task.id, new_done)

    # ── Events ────────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event) -> None:
        self.edit_requested.emit(self._task)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        start = getattr(self, "_drag_start", None)
        if start is None:
            return super().mouseMoveEvent(event)
        if (event.position().toPoint() - start).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)
        self._start_task_drag()

    def _start_task_drag(self) -> None:
        mime = QMimeData()
        mime.setData(_TASK_MIME, str(self._task.id).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        pix = self.grab()
        drag.setPixmap(pix.scaled(
            pix.width() // 2, pix.height() // 2,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        drag.exec(Qt.DropAction.MoveAction)

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

        # Done overlay — dim the card when task is done
        if self._task.is_done:
            if self._is_dark:
                p.fillPath(clip, QColor(0, 0, 0, 90))
            else:
                p.fillPath(clip, QColor(255, 255, 255, 90))

        p.setClipping(False)

        # Border: green when done, orange otherwise
        if self._task.is_done:
            alpha = 180 if self._hovered else 120
            col   = QColor(34, 197, 94, alpha)
        else:
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
