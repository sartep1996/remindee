import enum
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .user import User


class FrequencyType(enum.Enum):
    OFTEN = "often"       # every 1 hour
    MEDIUM = "medium"     # every 6 hours
    RARELY = "rarely"     # every 24 hours
    RANDOM = "random"     # random interval 1–24 hours, rescheduled after each fire
    SPECIFIC = "specific" # exact one-time datetime


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    frequency: Mapped[FrequencyType] = mapped_column(Enum(FrequencyType), nullable=False)
    specific_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_trigger: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    snooze_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship("User", back_populates="reminders")

    def __repr__(self) -> str:
        return f"<Reminder id={self.id} name={self.name!r} freq={self.frequency.value}>"
