from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .user import User
    from .note_folder import NoteFolder


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    folder_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("note_folders.id"), nullable=True, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    body_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    color_label: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    attachments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship("User", back_populates="notes")
    folder: Mapped[Optional["NoteFolder"]] = relationship(
        "NoteFolder", back_populates="notes"
    )

    def __repr__(self) -> str:
        return f"<Note id={self.id} title={self.title!r}>"
