"""ARQ worker configuration with bounded retries."""

from typing import ClassVar

from arq.connections import RedisSettings

from app.config import get_settings
from app.scheduler.jobs import (
    appointment_followup_call,
    appointment_reminder_call,
    create_recurring_medication_dose,
    family_notification,
    generic_outbound_reminder,
    low_stock_notification,
    medication_no_answer_retry,
    medication_reminder_call,
    safety_escalation,
    safety_reminder_call,
    safety_retry,
)


class WorkerSettings:
    functions: ClassVar[list[object]] = [
        generic_outbound_reminder,
        create_recurring_medication_dose,
        medication_reminder_call,
        medication_no_answer_retry,
        low_stock_notification,
        safety_reminder_call,
        safety_retry,
        safety_escalation,
        appointment_reminder_call,
        appointment_followup_call,
        family_notification,
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 20
    job_timeout = 120
    max_tries = 3
    keep_result = 3600
