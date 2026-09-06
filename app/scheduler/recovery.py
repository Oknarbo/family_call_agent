"""Rebuild Redis jobs from committed SQL outbox records."""

from datetime import datetime
from typing import Any

from app.schemas import OutboundCallRecord


async def enqueue_calls(redis: Any, calls: list[OutboundCallRecord], *, now: datetime, batch_size: int = 100) -> int:
    queued = 0
    for call in calls:
        job = await redis.enqueue_job(
            "dispatch_outbound_call",
            str(call.id),
            _job_id=f"outbound:{call.id}",
            _defer_until=max(now, call.scheduled_for),
        )
        if job is not None:
            queued += 1
        if queued >= batch_size:
            break
    return queued
