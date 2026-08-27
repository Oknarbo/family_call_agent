"""PostgreSQL-backed recovery of overdue work after downtime."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import OutboundCallStatus, ReminderStatus
from app.models import OutboundCall, Reminder


async def recover_overdue_jobs(session: AsyncSession, redis: Any, *, now: datetime, batch_size: int = 100) -> int:
    """Re-enqueue due source-of-truth rows using stable ARQ job IDs."""

    reminders = (
        await session.scalars(
            select(Reminder)
            .where(Reminder.status == ReminderStatus.SCHEDULED, Reminder.scheduled_for <= now)
            .order_by(Reminder.scheduled_for)
            .limit(batch_size)
        )
    ).all()
    remaining = max(batch_size - len(reminders), 0)
    calls = (
        await session.scalars(
            select(OutboundCall)
            .where(
                OutboundCall.status == OutboundCallStatus.SCHEDULED,
                OutboundCall.scheduled_for <= now,
            )
            .order_by(OutboundCall.scheduled_for)
            .limit(remaining)
        )
    ).all()
    for reminder in reminders:
        await redis.enqueue_job(
            "generic_outbound_reminder",
            str(reminder.id),
            reminder.idempotency_key,
            _job_id=f"reminder:{reminder.idempotency_key}",
        )
    for call in calls:
        await redis.enqueue_job(
            "generic_outbound_reminder",
            str(call.id),
            call.idempotency_key,
            _job_id=f"outbound:{call.idempotency_key}",
        )
    return len(reminders) + len(calls)
