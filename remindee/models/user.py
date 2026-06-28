from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .reminder import Reminder
    from .note_folder import NoteFolder
    from .note import Note


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    google_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)
    google_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    google_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    theme: Mapped[str] = mapped_column(String(16), default="system")
    app_font: Mapped[str] = mapped_column(String(128), nullable=False, server_default="Marker Felt")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    reminders: Mapped[List["Reminder"]] = relationship(
        "Reminder", back_populates="user", cascade="all, delete-orphan"
    )
    note_folders: Mapped[List["NoteFolder"]] = relationship(
        "NoteFolder", back_populates="user", cascade="all, delete-orphan"
    )
    notes: Mapped[List["Note"]] = relationship(
        "Note", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
