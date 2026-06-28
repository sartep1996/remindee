from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .user import User
    from .note import Note


class NoteFolder(Base):
    __tablename__ = "note_folders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="note_folders")
    notes: Mapped[List["Note"]] = relationship(
        "Note", back_populates="folder", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<NoteFolder id={self.id} name={self.name!r}>"
