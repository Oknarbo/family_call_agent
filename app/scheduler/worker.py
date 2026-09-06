"""Periodic SQL recovery and one canonical dispatch job."""

from datetime import UTC
from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings
from arq.worker import func

from app.config import get_settings
from app.scheduler.jobs import dispatch_outbound_call, generic_outbound_reminder, scheduler_tick

LEGACY_JOBS = (
    "generic_outbound_reminder",
    "create_recurring_medication_dose",
    "medication_reminder_call",
    "medication_no_answer_retry",
    "low_stock_notification",
    "safety_reminder_call",
    "safety_retry",
    "safety_escalation",
    "appointment_reminder_call",
    "appointment_followup_call",
    "family_notification",
)


class WorkerSettings:
    functions: ClassVar[list[object]] = [
        dispatch_outbound_call,
        scheduler_tick,
        *(func(generic_outbound_reminder, name=name, keep_result=0) for name in LEGACY_JOBS),
    ]
    cron_jobs: ClassVar[list[object]] = [
        cron(scheduler_tick, second=set(range(0, 60, 5)), microsecond=0, run_at_startup=True, keep_result=0)
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    timezone = UTC
    max_jobs = 20
    job_timeout = 120
    max_tries = 3
    # SQL is the durable deduplication authority. Completed Redis results must
    # not prevent a not-yet-due or temporarily busy call from being recovered.
    keep_result = 0
