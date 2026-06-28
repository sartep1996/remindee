from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from .config import DATABASE_URL
from remindee.models.base import Base
import remindee.models.user  # noqa: F401 — registers User with Base.metadata
import remindee.models.reminder  # noqa: F401 — registers Reminder with Base.metadata
import remindee.models.note_folder  # noqa: F401 — registers NoteFolder with Base.metadata
import remindee.models.note  # noqa: F401 — registers Note with Base.metadata

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
