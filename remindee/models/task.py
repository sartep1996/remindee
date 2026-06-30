from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User


class TaskStatus(enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS  = "in_progress"
    BLOCKED      = "blocked"
    COMPLETED    = "completed"
    CANCELLED    = "cancelled"


class TaskPriority(enum.Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"
    URGENT = "urgent"


class Task(Base):
    __tablename__ = "tasks"

    id              : Mapped[int]            = mapped_column(primary_key=True, autoincrement=True)
    user_id         : Mapped[int]            = mapped_column(ForeignKey("users.id"), index=True)
    parent_id       : Mapped[Optional[int]]  = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    title           : Mapped[str]            = mapped_column(String(512), nullable=False)
    description     : Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    status          : Mapped[TaskStatus]     = mapped_column(SAEnum(TaskStatus), default=TaskStatus.NOT_STARTED, nullable=False)
    priority        : Mapped[TaskPriority]   = mapped_column(SAEnum(TaskPriority), default=TaskPriority.MEDIUM, nullable=False)
    due_date        : Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completion_date : Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sort_order      : Mapped[int]            = mapped_column(Integer, default=0)
    created_at      : Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow)
    updated_at      : Mapped[datetime]       = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="tasks")

    # Self-referential hierarchy — cascade ensures children are deleted with parent
    parent: Mapped[Optional["Task"]] = relationship(
        "Task",
        foreign_keys="[Task.parent_id]",
        remote_side="Task.id",
        back_populates="children",
    )
    children: Mapped[List["Task"]] = relationship(
        "Task",
        foreign_keys="[Task.parent_id]",
        back_populates="parent",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r} status={self.status.value}>"
