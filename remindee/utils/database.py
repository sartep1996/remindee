from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from .config import DATABASE_URL
from remindee.models.base import Base
# Side-effect imports — register all ORM models with Base.metadata before
# create_all() is called. Import as symbols to satisfy pyflakes.
from remindee.models.user import User as _User
from remindee.models.reminder import Reminder as _Reminder
from remindee.models.note_folder import NoteFolder as _NoteFolder
from remindee.models.note import Note as _Note
from remindee.models.task import Task as _Task

__all__ = ["init_db", "get_session", "SessionLocal", "engine",
           "_User", "_Reminder", "_NoteFolder", "_Note", "_Task"]

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    # pool_pre_ping evicts stale connections that would otherwise surface as
    # "database is locked" errors when APScheduler's background thread races
    # with the main thread under SQLite's default serialised-writes behaviour.
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    # Migrate existing DBs: add columns that may not exist yet
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE reminders ADD COLUMN font_family VARCHAR(128) NOT NULL DEFAULT 'Marker Felt'",
            "ALTER TABLE users ADD COLUMN app_font VARCHAR(128) NOT NULL DEFAULT 'Marker Felt'",
            "ALTER TABLE notes ADD COLUMN attachments TEXT",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists


@contextmanager
def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
