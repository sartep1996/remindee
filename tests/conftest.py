"""
conftest.py — test-suite root configuration.

CRITICAL ORDERING RULE
----------------------
`remindee.utils.config` reads DATABASE_URL at *import time* via os.getenv().
`remindee.utils.database` then calls create_engine(DATABASE_URL) at *import time*.

We must therefore:
  1. Set DATABASE_URL in os.environ BEFORE any remindee import.
  2. Ensure remindee.utils.database is imported (triggering its side-effect model
     imports) BEFORE calling Base.metadata.create_all() on the test engine —
     otherwise Base.metadata is empty and no tables are created.
  3. Patch the already-created `engine` + `SessionLocal` on every test that
     hits the DB, so tests are isolated from each other and from the on-disk
     production DB.

Strategy: per-test StaticPool SQLite in-memory engine (each test gets its own
in-memory database). StaticPool reuses the single DBAPI connection across all
SessionLocal() calls within the same test, which is the only way multiple
sessions can see the same schema/data in a :memory: DB. Tables are created
before the test and dropped (via engine.dispose()) at teardown.
"""
import os
import sys

# ── 1. Pin the database before any remindee import ─────────────────────────
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# Headless Qt for all UI tests
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ── 2. Ensure the package root is on sys.path ───────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── 3. Trigger model registration with Base.metadata NOW, at conftest load
#       time.  This import is what causes remindee.models.user and
#       remindee.models.reminder to be imported (see the noqa lines in
#       database.py) so that their Table objects are registered with Base.
#       Any fixture that calls Base.metadata.create_all() will then see the
#       correct table set.
import remindee.utils.database  # noqa: F401 — side-effect: registers models

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ── 4. QApplication must exist before any Qt widget is created ──────────────
@pytest.fixture(scope="session")
def qapp():
    """Shared QApplication for the entire test session (headless)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(scope="function")
def db_engine():
    """
    Per-test SQLite in-memory engine with a single shared connection.

    StaticPool + check_same_thread=False let SQLAlchemy reuse the *same*
    in-memory connection for every session created during the test, which is
    the only way multiple SessionLocal() calls can see the same schema in a
    :memory: DB.  Tables are created before the test and the engine is disposed
    (releasing the StaticPool connection) at teardown so no state bleeds between
    tests.

    IMPORTANT: remindee.utils.database must already be imported before this
    fixture runs so that Base.metadata contains the User and Reminder table
    definitions.  The module-level import above guarantees this.
    """
    from remindee.models.base import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Base.metadata is now populated (models imported at conftest load time)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def patched_db(db_engine, monkeypatch):
    """
    Monkey-patch remindee.utils.database so that every call to get_session()
    or SessionLocal() inside the app code hits the isolated in-memory engine
    for the duration of the test.

    monkeypatch restores the originals automatically after the test, so the
    next test gets a pristine module state.
    """
    import remindee.utils.database as db_module

    TestSession = sessionmaker(db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(db_module, "engine", db_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)
    return db_module


@pytest.fixture(scope="function")
def sample_user(patched_db):
    """
    A persisted User row for tests that need an existing user in the DB.
    Returns a detached User instance.
    """
    from remindee.services.auth_service import LocalAuthService
    return LocalAuthService.register("testuser", "test@example.com", "S3cur3P@ss!")
