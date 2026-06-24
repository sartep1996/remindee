from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from PySide6.QtCore import QObject, Signal

from remindee.models.reminder import Reminder, FrequencyType
from remindee.utils.database import get_session


class SchedulerSignals(QObject):
    triggered = Signal(int)  # reminder_id — emitted from background thread, queued to main


class SchedulerService:
    def __init__(self) -> None:
        self.signals = SchedulerSignals()
        # Use in-memory job store — jobs are rebuilt from DB on each start()
        self._scheduler = BackgroundScheduler(daemon=True)
        self._user_id: Optional[int] = None

    def start(self, user_id: int) -> None:
        self._user_id = user_id
        if not self._scheduler.running:
            self._scheduler.start()
        self._load_user_reminders(user_id)

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _load_user_reminders(self, user_id: int) -> None:
        with get_session() as session:
            reminders = (
                session.query(Reminder)
                .filter_by(user_id=user_id, is_active=True, is_done=False)
                .all()
            )
            for r in reminders:
                session.expunge(r)

        for reminder in reminders:
            self.schedule_reminder(reminder)

    def schedule_reminder(self, reminder: Reminder) -> None:
        job_id = f"reminder_{reminder.id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        now = datetime.utcnow()

        if reminder.frequency == FrequencyType.SPECIFIC:
            if reminder.specific_datetime and reminder.specific_datetime > now:
                self._scheduler.add_job(
                    self._on_trigger,
                    trigger=DateTrigger(run_date=reminder.specific_datetime),
                    id=job_id,
                    args=[reminder.id],
                    replace_existing=True,
                )
        elif reminder.frequency == FrequencyType.OFTEN:
            self._scheduler.add_job(
                self._on_trigger,
                trigger=IntervalTrigger(hours=1, start_date=now + timedelta(seconds=5)),
                id=job_id,
                args=[reminder.id],
                replace_existing=True,
            )
        elif reminder.frequency == FrequencyType.MEDIUM:
            self._scheduler.add_job(
                self._on_trigger,
                trigger=IntervalTrigger(hours=6, start_date=now + timedelta(seconds=5)),
                id=job_id,
                args=[reminder.id],
                replace_existing=True,
            )
        elif reminder.frequency == FrequencyType.RARELY:
            self._scheduler.add_job(
                self._on_trigger,
                trigger=IntervalTrigger(hours=24, start_date=now + timedelta(seconds=5)),
                id=job_id,
                args=[reminder.id],
                replace_existing=True,
            )
        elif reminder.frequency == FrequencyType.RANDOM:
            hours = random.randint(1, 24)
            self._scheduler.add_job(
                self._on_trigger_random,
                trigger=DateTrigger(run_date=now + timedelta(hours=hours)),
                id=job_id,
                args=[reminder.id],
                replace_existing=True,
            )

        # Update next_trigger in DB
        job = self._scheduler.get_job(job_id)
        if job and job.next_run_time:
            with get_session() as session:
                db_reminder = session.get(Reminder, reminder.id)
                if db_reminder:
                    db_reminder.next_trigger = job.next_run_time.replace(tzinfo=None)

    def reschedule_reminder(self, reminder: Reminder) -> None:
        self.schedule_reminder(reminder)

    def remove_reminder(self, reminder_id: int) -> None:
        job_id = f"reminder_{reminder_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    def _on_trigger(self, reminder_id: int) -> None:
        self.signals.triggered.emit(reminder_id)

    def _on_trigger_random(self, reminder_id: int) -> None:
        self.signals.triggered.emit(reminder_id)
        # Reschedule for next random interval
        reminder = None  # guard against NameError if session.get() raises before assignment
        with get_session() as session:
            reminder = session.get(Reminder, reminder_id)
            if reminder and reminder.is_active and not reminder.is_done:
                session.expunge(reminder)
            else:
                reminder = None
        if reminder:
            self.schedule_reminder(reminder)
