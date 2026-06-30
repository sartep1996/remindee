from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from remindee.models.task import Task, TaskPriority, TaskStatus
from remindee.utils.database import get_session


# ── Module-level helper ───────────────────────────────────────────────────────

def compute_progress(
    task_id: int,
    tasks_by_parent: dict[int, list[Task]],
    task_by_id: dict[int, Task],
) -> tuple[int, int]:
    """Recursively count (completed, total) leaf tasks under task_id."""
    children = tasks_by_parent.get(task_id, [])
    if not children:
        task = task_by_id.get(task_id)
        if task is None:
            return 0, 0
        done = task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        return (1 if done else 0), 1
    completed = total = 0
    for child in children:
        c, t = compute_progress(child.id, tasks_by_parent, task_by_id)
        completed += c
        total += t
    return completed, total


# ── Service ───────────────────────────────────────────────────────────────────

class TaskService:

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_all_for_user(self, user_id: int) -> list[Task]:
        """Return every task for this user as a flat, expunged list."""
        with get_session() as session:
            tasks = (
                session.query(Task)
                .filter(Task.user_id == user_id)
                .order_by(Task.sort_order, Task.created_at)
                .all()
            )
            for t in tasks:
                session.expunge(t)
            return tasks

    def get_due_today(self, user_id: int) -> list[Task]:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end   = today_start + timedelta(days=1)
        with get_session() as session:
            tasks = (
                session.query(Task)
                .filter(
                    Task.user_id == user_id,
                    Task.due_date >= today_start,
                    Task.due_date < today_end,
                    Task.status.notin_([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
                )
                .order_by(Task.priority.desc(), Task.due_date)
                .all()
            )
            for t in tasks:
                session.expunge(t)
            return tasks

    def get_overdue(self, user_id: int) -> list[Task]:
        now = datetime.utcnow()
        with get_session() as session:
            tasks = (
                session.query(Task)
                .filter(
                    Task.user_id == user_id,
                    Task.due_date.isnot(None),
                    Task.due_date < now,
                    Task.status.notin_([TaskStatus.COMPLETED, TaskStatus.CANCELLED]),
                )
                .order_by(Task.due_date)
                .all()
            )
            for t in tasks:
                session.expunge(t)
            return tasks

    def get_completed(self, user_id: int) -> list[Task]:
        with get_session() as session:
            tasks = (
                session.query(Task)
                .filter(Task.user_id == user_id, Task.status == TaskStatus.COMPLETED)
                .order_by(Task.completion_date.desc())
                .all()
            )
            for t in tasks:
                session.expunge(t)
            return tasks

    def get_task(self, task_id: int) -> Optional[Task]:
        with get_session() as session:
            t = session.get(Task, task_id)
            if t:
                session.expunge(t)
            return t

    # ── Mutations ────────────────────────────────────────────────────────────

    def create_task(
        self,
        user_id: int,
        title: str,
        parent_id: Optional[int] = None,
        description: Optional[str] = None,
        status: TaskStatus = TaskStatus.NOT_STARTED,
        priority: TaskPriority = TaskPriority.MEDIUM,
        due_date: Optional[datetime] = None,
    ) -> Task:
        with get_session() as session:
            task = Task(
                user_id=user_id,
                parent_id=parent_id,
                title=title,
                description=description,
                status=status,
                priority=priority,
                due_date=due_date,
            )
            session.add(task)
            session.flush()
            session.expunge(task)
            return task

    def update_task(self, task_id: int, **kwargs) -> Task:
        with get_session() as session:
            task = session.query(Task).filter(Task.id == task_id).one()
            for key, value in kwargs.items():
                setattr(task, key, value)
            session.flush()
            session.expunge(task)
            return task

    def toggle_complete(self, task_id: int) -> Task:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(task_id)
        if task.status == TaskStatus.COMPLETED:
            return self.update_task(task_id, status=TaskStatus.NOT_STARTED, completion_date=None)
        return self.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            completion_date=datetime.utcnow(),
        )

    def set_status(self, task_id: int, status: TaskStatus) -> Task:
        kwargs: dict = {"status": status}
        if status == TaskStatus.COMPLETED:
            kwargs["completion_date"] = datetime.utcnow()
        elif status != TaskStatus.COMPLETED:
            kwargs["completion_date"] = None
        return self.update_task(task_id, **kwargs)

    def delete_task(self, task_id: int) -> None:
        with get_session() as session:
            task = session.query(Task).filter(Task.id == task_id).one()
            session.delete(task)

    # ── Tree helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def build_index(tasks: list[Task]) -> tuple[dict, dict]:
        """Return (tasks_by_parent, task_by_id) from a flat list."""
        by_parent: dict[int | None, list[Task]] = {}
        by_id: dict[int, Task] = {}
        for t in tasks:
            by_parent.setdefault(t.parent_id, []).append(t)
            by_id[t.id] = t
        return by_parent, by_id
