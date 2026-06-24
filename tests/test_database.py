"""
PASS 1 — Boundary Contradiction Sweep: database layer.

Tests:
- init_db() creates all expected tables without error
- get_session() commits on clean exit (data persists)
- get_session() rolls back on exception (data is not persisted)
- Multiple sequential get_session() calls do not leak connections
- get_session() propagates the original exception after rollback
"""
import pytest


# ─── helpers ────────────────────────────────────────────────────────────────

def _table_names(engine) -> set:
    from sqlalchemy import inspect
    return set(inspect(engine).get_table_names())


# ─── tests ──────────────────────────────────────────────────────────────────

class TestInitDb:
    def test_creates_users_table(self, db_engine, patched_db):
        from remindee.utils.database import init_db
        # tables are already created by the db_engine fixture; verify they exist
        init_db()  # idempotent — must not raise
        assert "users" in _table_names(db_engine)

    def test_creates_reminders_table(self, db_engine, patched_db):
        from remindee.utils.database import init_db
        init_db()
        assert "reminders" in _table_names(db_engine)

    def test_init_db_is_idempotent(self, db_engine, patched_db):
        """Calling init_db() twice must not raise (checkfirst=True behaviour)."""
        from remindee.utils.database import init_db
        init_db()
        init_db()  # second call — must be silent


class TestGetSession:
    def test_commits_on_clean_exit(self, patched_db):
        """Data written inside get_session() survives after the context exits."""
        from remindee.utils.database import get_session, SessionLocal
        from remindee.models.user import User

        with get_session() as s:
            s.add(User(email="commit@example.com", password_hash="x"))

        # Open a new session to verify the row was committed
        verify_session = SessionLocal()
        try:
            user = verify_session.query(User).filter_by(email="commit@example.com").first()
            assert user is not None
            assert user.email == "commit@example.com"
        finally:
            verify_session.close()

    def test_rolls_back_on_exception(self, patched_db):
        """
        Data written inside get_session() MUST NOT persist when an exception
        is raised before the context exits.
        """
        from remindee.utils.database import get_session, SessionLocal
        from remindee.models.user import User

        with pytest.raises(RuntimeError):
            with get_session() as s:
                s.add(User(email="rollback@example.com", password_hash="x"))
                raise RuntimeError("forced failure")

        verify_session = SessionLocal()
        try:
            user = verify_session.query(User).filter_by(email="rollback@example.com").first()
            assert user is None, "Rolled-back user must not be visible in a new session"
        finally:
            verify_session.close()

    def test_propagates_original_exception(self, patched_db):
        """get_session() must re-raise the exception after rolling back."""
        from remindee.utils.database import get_session

        class _Sentinel(Exception):
            pass

        with pytest.raises(_Sentinel):
            with get_session() as _s:
                raise _Sentinel("must propagate")

    def test_multiple_sequential_sessions_no_leak(self, patched_db):
        """
        Calling get_session() N times sequentially must not exhaust the pool
        or leave open connections behind (StaticPool reuses the same connection
        so this effectively tests proper close() calls).
        """
        from remindee.utils.database import get_session
        from remindee.models.user import User

        for i in range(10):
            with get_session() as s:
                s.add(User(email=f"seq{i}@example.com", password_hash="x"))
        # If we reach here without pool errors, no leak occurred.

    def test_session_no_open_transaction_after_exception(self, patched_db):
        """
        After an exception inside get_session(), the session must NOT hold an
        open transaction (the rollback must have completed).

        SQLAlchemy 2.0 changed session.is_active semantics — it stays True even
        after rollback+close.  The correct post-exception invariant in SA 2.0 is
        that session.in_transaction() returns False (the DBAPI connection was
        returned to the pool and no BEGIN is outstanding).
        """
        from remindee.utils.database import get_session

        captured = {}

        with pytest.raises(ValueError):
            with get_session() as s:
                captured["session"] = s
                raise ValueError("boom")

        # SA 2.0: in_transaction() == False means the session is not holding an
        # open DBAPI transaction — rollback + close completed successfully.
        assert not captured["session"].in_transaction(), (
            "Session must not hold an open transaction after exception + rollback"
        )
