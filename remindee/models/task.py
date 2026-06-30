from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User


class Task(Base):
    __tablename__ = "tasks"

    id              : Mapped[int]               = mapped_column(primary_key=True, autoincrement=True)
    user_id         : Mapped[int]               = mapped_column(ForeignKey("users.id"), index=True)
    title           : Mapped[str]               = mapped_column(String(512), nullable=False)
    status          : Mapped[str]               = mapped_column(String(32),  nullable=False, default="pending")
    priority        : Mapped[str]               = mapped_column(String(16),  nullable=False, default="medium")
    sort_order      : Mapped[int]               = mapped_column(Integer,     nullable=False, default=0)
    is_done         : Mapped[bool]              = mapped_column(Boolean,     nullable=False, default=False)
    due_date        : Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completion_date : Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # JSON list: [{"title": str, "done": bool}, ...]
    subtasks        : Mapped[Optional[str]]     = mapped_column(Text, nullable=True)
    description     : Mapped[Optional[str]]     = mapped_column(Text, nullable=True)
    created_at      : Mapped[datetime]          = mapped_column(DateTime, default=datetime.utcnow)
    updated_at      : Mapped[datetime]          = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="tasks")

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r}>"
