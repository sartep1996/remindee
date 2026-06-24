"""
PASS 1 — Boundary Contradiction Sweep: Reminder model + scheduler.

Boundary matrix for schedule_reminder():
  frequency : OFTEN / MEDIUM / RARELY / RANDOM / SPECIFIC (all five branches)
  SPECIFIC  : future datetime (job added), past datetime (NO job added), None (no job)
  start()   : called twice — must not double-register jobs

PASS 2 — Mock Reality Check:
  We do NOT mock APScheduler. We let the real BackgroundScheduler run but
  immediately shut it down after each test. We verify job existence via
  scheduler.get_job(), which is the real APScheduler API.

PASS 3 — State teardown:
  - `scheduler` fixture starts the scheduler and shuts it down in teardown.
  - `patched_db` ensures the in-memory test DB is used.
  - `sample_user` provides a persisted User so foreign-key constraints pass.

NOTE on SchedulerSignals:
  SchedulerSignals(QObject) emits Qt signals from a background thread (queued
  connection). Instantiation must happen on the main thread. The `qapp` fixture
  ensures a QApplication exists; QObject instantiation is then legal on the
  calling thread (pytest's main thread).
"""
import pytest
from datetime import datetime, timedelta


@pytest.fixture(scope="function")
def scheduler(patched_db, qapp):
    """
    A fresh SchedulerService per test, started and stopped cleanly.
    The scheduler is NOT loaded with user reminders here — individual tests
    drive schedule_reminder() directly.
    """
    from remindee.services.scheduler_service import SchedulerService
    svc = SchedulerService()
    svc._scheduler.start()
    yield svc
    if svc._scheduler.running:
        svc._scheduler.shutdown(wait=False)


def _make_reminder(user_id, frequency, specific_datetime=None, reminder_id=999):
    """
    Build a minimal reminder-like namespace for scheduler tests.

    SQLAlchemy 2.0 ORM instances require _sa_instance_state to be initialised
    by __init__; bypassing it with __new__ raises AttributeError when any
    mapped attribute is assigned.  SchedulerService only reads .id, .frequency,
    .specific_datetime, .is_active, .is_done from a Reminder — so a plain
    SimpleNamespace with those attributes is sufficient and avoids SA machinery.
    """
    from types import SimpleNamespace
    return SimpleNamespace(
        id=reminder_id,
        user_id=user_id,
        name="Test reminder",
        details=None,
        frequency=frequency,
        specific_datetime=specific_datetime,
        next_trigger=None,
        is_done=False,
        is_active=True,
        snooze_until=None,
    )


# ─── Reminder model persistence ─────────────────────────────────────────────

class TestReminderPersistence:
    def test_reminder_persists_and_loads(self, patched_db, sample_user):
        """A Reminder saved through a session must be retrievable in a new session."""
        from remindee.utils.database import get_session, SessionLocal
        from remindee.models.reminder import Reminder, FrequencyType

        with get_session() as s:
            r = Reminder(
                user_id=sample_user.id,
                name="Buy milk",
                details="Semi-skimmed",
                frequency=FrequencyType.OFTEN,
                is_active=True,
                is_done=False,
            )
            s.add(r)
            s.flush()
            saved_id = r.id

        session2 = SessionLocal()
        try:
            loaded = session2.get(Reminder, saved_id)
            assert loaded is not None
            assert loaded.name == "Buy milk"
            assert loaded.frequency == FrequencyType.OFTEN
            assert loaded.details == "Semi-skimmed"
        finally:
            session2.close()

    def test_reminder_frequency_enum_roundtrip(self, patched_db, sample_user):
        """All FrequencyType values must survive a DB roundtrip unchanged."""
        from remindee.utils.database import get_session, SessionLocal
        from remindee.models.reminder import Reminder, FrequencyType

        freq_ids = {}
        for freq in FrequencyType:
            with get_session() as s:
                r = Reminder(
                    user_id=sample_user.id,
                    name=f"r_{freq.value}",
                    frequency=freq,
                )
                s.add(r)
                s.flush()
                freq_ids[freq] = r.id

        session2 = SessionLocal()
        try:
            for freq, rid in freq_ids.items():
                loaded = session2.get(Reminder, rid)
                assert loaded.frequency == freq, (
                    f"FrequencyType.{freq.name} did not survive DB roundtrip"
                )
        finally:
            session2.close()

    def test_reminder_cascade_deletes_on_user_delete(self, patched_db, sample_user):
        """Deleting a User must cascade-delete their Reminders (FK + cascade setting)."""
        from remindee.utils.database import get_session, SessionLocal
        from remindee.models.reminder import Reminder, FrequencyType
        from remindee.models.user import User

        with get_session() as s:
            r = Reminder(
                user_id=sample_user.id,
                name="Orphan",
                frequency=FrequencyType.RARELY,
            )
            s.add(r)
            s.flush()
            reminder_id = r.id

        with get_session() as s:
            user = s.get(User, sample_user.id)
            s.delete(user)

        session2 = SessionLocal()
        try:
            gone = session2.get(Reminder, reminder_id)
            assert gone is None, "Reminder must be cascade-deleted with its user"
        finally:
            session2.close()


# ─── Scheduler: job creation ─────────────────────────────────────────────────

class TestScheduleReminder:
    def test_often_frequency_adds_job(self, scheduler, sample_user):
        from remindee.models.reminder import FrequencyType
        r = _make_reminder(sample_user.id, FrequencyType.OFTEN)
        scheduler.schedule_reminder(r)
        assert scheduler._scheduler.get_job("reminder_999") is not None

    def test_medium_frequency_adds_job(self, scheduler, sample_user):
        from remindee.models.reminder import FrequencyType
        r = _make_reminder(sample_user.id, FrequencyType.MEDIUM, reminder_id=1001)
        scheduler.schedule_reminder(r)
        assert scheduler._scheduler.get_job("reminder_1001") is not None

    def test_rarely_frequency_adds_job(self, scheduler, sample_user):
        from remindee.models.reminder import FrequencyType
        r = _make_reminder(sample_user.id, FrequencyType.RARELY, reminder_id=1002)
        scheduler.schedule_reminder(r)
        assert scheduler._scheduler.get_job("reminder_1002") is not None

    def test_random_frequency_adds_job(self, scheduler, sample_user):
        from remindee.models.reminder import FrequencyType
        r = _make_reminder(sample_user.id, FrequencyType.RANDOM, reminder_id=1003)
        scheduler.schedule_reminder(r)
        assert scheduler._scheduler.get_job("reminder_1003") is not None

    def test_specific_future_adds_job(self, scheduler, sample_user):
        """
        A SPECIFIC reminder whose specific_datetime is in the future (from
        schedule_reminder's perspective, which uses datetime.utcnow()) must
        add a job.

        TIMEZONE NOTE: APScheduler's DateTrigger interprets naive datetimes as
        local time by default.  The app code compares against datetime.utcnow()
        (naive UTC) to decide whether to schedule, but APScheduler then treats
        the same naive datetime as local.  On a UTC+N machine, a datetime that
        is N hours ahead of UTC-now will appear to be already-past to APScheduler
        the moment the job is added.

        To avoid this race we schedule far enough in the future that no
        realistic UTC offset can make the run_date appear past to APScheduler:
        we use 48 hours (well beyond any UTC+14 extreme).  For the same reason
        we verify the job exists immediately after adding, before the background
        thread has any opportunity to execute it.
        """
        from remindee.models.reminder import FrequencyType
        # 48 hours guarantees future from both UTC and local perspective on any
        # UTC offset in the range [-12, +14]
        future_dt = datetime.utcnow() + timedelta(hours=48)
        r = _make_reminder(sample_user.id, FrequencyType.SPECIFIC,
                           specific_datetime=future_dt, reminder_id=1004)
        scheduler.schedule_reminder(r)
        assert scheduler._scheduler.get_job("reminder_1004") is not None

    def test_specific_past_does_not_add_job(self, scheduler, sample_user):
        """
        SPECIFIC reminder with a datetime in the past MUST NOT be scheduled.
        This is the key business rule: expired one-time reminders are silently
        skipped in schedule_reminder().
        """
        from remindee.models.reminder import FrequencyType
        past_dt = datetime.utcnow() - timedelta(hours=1)
        r = _make_reminder(sample_user.id, FrequencyType.SPECIFIC,
                           specific_datetime=past_dt, reminder_id=1005)
        scheduler.schedule_reminder(r)
        assert scheduler._scheduler.get_job("reminder_1005") is None

    def test_specific_none_datetime_does_not_add_job(self, scheduler, sample_user):
        """
        SPECIFIC reminder with specific_datetime=None must not add a job
        (the None guard in schedule_reminder() covers this).
        """
        from remindee.models.reminder import FrequencyType
        r = _make_reminder(sample_user.id, FrequencyType.SPECIFIC,
                           specific_datetime=None, reminder_id=1006)
        scheduler.schedule_reminder(r)
        assert scheduler._scheduler.get_job("reminder_1006") is None

    def test_specific_exactly_now_does_not_add_job(self, scheduler, sample_user):
        """
        A SPECIFIC datetime equal to utcnow() (the boundary second) must NOT
        be scheduled — the condition is strict `> now`.
        """
        from remindee.models.reminder import FrequencyType
        # Use a datetime that is definitely <= now
        boundary_dt = datetime.utcnow() - timedelta(microseconds=1)
        r = _make_reminder(sample_user.id, FrequencyType.SPECIFIC,
                           specific_datetime=boundary_dt, reminder_id=1007)
        scheduler.schedule_reminder(r)
        assert scheduler._scheduler.get_job("reminder_1007") is None

    def test_reschedule_replaces_existing_job(self, scheduler, sample_user):
        """Calling schedule_reminder() twice on the same id must not duplicate the job."""
        from remindee.models.reminder import FrequencyType
        r = _make_reminder(sample_user.id, FrequencyType.OFTEN, reminder_id=1008)
        scheduler.schedule_reminder(r)
        scheduler.schedule_reminder(r)
        jobs = [j for j in scheduler._scheduler.get_jobs() if j.id == "reminder_1008"]
        assert len(jobs) == 1, "Only one job must exist after double schedule_reminder()"


# ─── Scheduler: job removal ──────────────────────────────────────────────────

class TestRemoveReminder:
    def test_remove_existing_job(self, scheduler, sample_user):
        from remindee.models.reminder import FrequencyType
        r = _make_reminder(sample_user.id, FrequencyType.OFTEN, reminder_id=2001)
        scheduler.schedule_reminder(r)
        assert scheduler._scheduler.get_job("reminder_2001") is not None
        scheduler.remove_reminder(2001)
        assert scheduler._scheduler.get_job("reminder_2001") is None

    def test_remove_nonexistent_job_does_not_raise(self, scheduler):
        """remove_reminder() on an unknown id must be a no-op, not an exception."""
        scheduler.remove_reminder(99999)

    def test_remove_already_removed_job_does_not_raise(self, scheduler, sample_user):
        """Double-remove must not crash (idempotency)."""
        from remindee.models.reminder import FrequencyType
        r = _make_reminder(sample_user.id, FrequencyType.MEDIUM, reminder_id=2002)
        scheduler.schedule_reminder(r)
        scheduler.remove_reminder(2002)
        scheduler.remove_reminder(2002)  # second call must be silent


# ─── Scheduler: start() called twice ─────────────────────────────────────────

class TestSchedulerStartTwice:
    def test_start_twice_does_not_double_schedule(self, patched_db, sample_user, qapp):
        """
        start() guards with `if not self._scheduler.running`.  Calling it twice
        must not create duplicate jobs (no reminders in DB, so zero jobs expected).
        """
        from remindee.services.scheduler_service import SchedulerService
        svc = SchedulerService()
        try:
            svc.start(sample_user.id)
            svc.start(sample_user.id)  # second start — must be a no-op for the scheduler
            jobs = svc._scheduler.get_jobs()
            assert len(jobs) == 0, (
                "No reminders in DB, so zero jobs expected after double start()"
            )
        finally:
            if svc._scheduler.running:
                svc._scheduler.shutdown(wait=False)


# ─── SchedulerSignals instantiation ──────────────────────────────────────────

class TestSchedulerSignals:
    def test_signals_instantiate_on_main_thread(self, qapp):
        """SchedulerSignals(QObject) must instantiate without error on the main thread."""
        from remindee.services.scheduler_service import SchedulerSignals
        signals = SchedulerSignals()
        assert signals is not None

    def test_signals_has_triggered_signal(self, qapp):
        """SchedulerSignals must expose the `triggered` signal attribute."""
        from remindee.services.scheduler_service import SchedulerSignals
        signals = SchedulerSignals()
        assert hasattr(signals, "triggered")
