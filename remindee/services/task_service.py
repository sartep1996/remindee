from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from remindee.models.task import Task
from remindee.utils.database import get_session


class TaskService:

    def get_all_for_user(self, user_id: int) -> list[Task]:
        with get_session() as session:
            tasks = (
                session.query(Task)
                .filter(Task.user_id == user_id)
                .order_by(Task.created_at.desc())
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

    def create_task(
        self,
        user_id: int,
        title: str,
        due_date: Optional[datetime] = None,
        subtasks: Optional[list[dict]] = None,
        description: Optional[str] = None,
    ) -> Task:
        with get_session() as session:
            task = Task(
                user_id=user_id,
                title=title,
                due_date=due_date,
                subtasks=json.dumps(subtasks) if subtasks else None,
                description=description,
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

    def toggle_done(self, task_id: int, done: bool) -> Task:
        completion = datetime.utcnow() if done else None
        return self.update_task(task_id, is_done=done, completion_date=completion,
                                status="done" if done else "pending")

    def toggle_subtask(self, task_id: int, idx: int, done: bool) -> Task:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(task_id)
        subs = json.loads(task.subtasks) if task.subtasks else []
        if 0 <= idx < len(subs):
            subs[idx]["done"] = done
        return self.update_task(task_id, subtasks=json.dumps(subs))

    def add_subtask(self, task_id: int, title: str) -> Task:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(task_id)
        subs = json.loads(task.subtasks) if task.subtasks else []
        subs.append({"title": title, "done": False})
        return self.update_task(task_id, subtasks=json.dumps(subs))

    def reorder_subtasks(self, task_id: int, new_order: list) -> Task:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(task_id)
        subs = json.loads(task.subtasks) if task.subtasks else []
        reordered = [subs[i] for i in new_order if i < len(subs)]
        return self.update_task(task_id, subtasks=json.dumps(reordered))

    def delete_task(self, task_id: int) -> None:
        with get_session() as session:
            task = session.query(Task).filter(Task.id == task_id).one()
            session.delete(task)

    @staticmethod
    def parse_subtasks(task: Task) -> list[dict]:
        """Return subtasks as a list of {title, done} dicts."""
        if not task.subtasks:
            return []
        try:
            return json.loads(task.subtasks)
        except Exception:
            return []

    @staticmethod
    def progress(task: Task) -> tuple[int, int]:
        """Return (completed, total) for a task's subtasks."""
        subs = TaskService.parse_subtasks(task)
        if not subs:
            return 0, 0
        done = sum(1 for s in subs if s.get("done"))
        return done, len(subs)
