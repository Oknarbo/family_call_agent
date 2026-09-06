"""SQL claims surround, but never span, the external provider request."""

from typing import Any
from uuid import UUID

import structlog

from app.config import get_settings
from app.dependencies import application_store
from app.domain.enums import MedicationDoseStatus, OutboundCallStatus, ReminderStatus
from app.domain.exceptions import CallNotPlacedError
from app.scheduler.planner import IN_FLIGHT, SchedulerPlanner
from app.scheduler.recovery import enqueue_calls
from app.services.audit import write_audit
from app.services.voice_delivery import VoiceDeliveryService
from app.utils.datetime import utc_now

logger = structlog.get_logger(__name__)


async def scheduler_tick(ctx: dict[str, Any]) -> dict[str, int]:
    settings = ctx.get("settings") or get_settings()
    if settings.telephony_provider == "twilio" and not settings.twilio_outbound_enabled:
        return {"queued": 0, "pending": 0, "paused": 1}
    now = ctx.get("now") or utc_now()
    async with application_store(settings) as store:
        calls = SchedulerPlanner(store, settings).materialize(now)
    # Commit before enqueue. If Redis fails, the next tick recovers SQL rows.
    queued = await enqueue_calls(ctx["redis"], calls, now=now, batch_size=settings.scheduler_batch_size)
    return {"queued": queued, "pending": len(calls)}


async def dispatch_outbound_call(ctx: dict[str, Any], entity_id: str) -> dict[str, str]:
    settings = ctx.get("settings") or get_settings()
    if (
        settings.telephony_provider == "twilio"
        and not settings.twilio_outbound_enabled
        and not ctx.get("allow_twilio_test")
    ):
        return {"status": "outbound_disabled"}
    now = ctx.get("now") or utc_now()
    call_id = UUID(entity_id)
    async with application_store(settings) as store:
        call = store.outbound_calls.get(call_id)
        if call is None:
            return {"status": "not_found"}
        if call.status != OutboundCallStatus.SCHEDULED:
            return {"status": "duplicate_skipped"}
        if call.scheduled_for > now:
            return {"status": "not_due"}
        planner = SchedulerPlanner(store, settings)
        if not planner.dispatchable(call, now):
            call.status, call.updated_at = OutboundCallStatus.CANCELLED, now
            return {"status": "cancelled"}
        # Serialize calls to one person, even for distinct simultaneous reminders.
        if any(
            c.target_user_id == call.target_user_id and c.status in IN_FLIGHT for c in store.outbound_calls.values()
        ):
            return {"status": "recipient_busy"}
        phone = store.family_members[call.target_user_id].phone_number_e164
        call.status, call.started_at, call.updated_at = OutboundCallStatus.DIALING, now, now
        if call.related_entity_type == "reminder":
            reminder = store.reminders[call.related_entity_id]
            if not reminder.recurrence_rule:
                reminder.status = ReminderStatus.EXECUTING
        elif call.related_entity_type == "medication_dose" and call.target_user_id == (
            store.medication_doses[call.related_entity_id].user_id
        ):
            store.medication_doses[call.related_entity_id].status = MedicationDoseStatus.REMINDER_STARTED
        snapshot = call.model_copy(deep=True)
    # A crash from here on is uncertain delivery, never permission to dial again.
    delivery = ctx.get("voice_delivery") or VoiceDeliveryService(settings)
    try:
        placed = await delivery.send(snapshot, phone)
        if not placed.provider_call_id:
            raise ValueError("Missing provider identifier")
    except Exception as exc:
        known_failure = isinstance(exc, CallNotPlacedError)
        async with application_store(settings) as store:
            call = store.outbound_calls[call_id]
            if call.status == OutboundCallStatus.DIALING and call.provider_call_id is None:
                call.status = OutboundCallStatus.FAILED if known_failure else OutboundCallStatus.DELIVERY_UNKNOWN
                call.error_code = "call_not_placed" if known_failure else "provider_outcome_unknown"
                call.updated_at = ctx.get("now") or utc_now()
                write_audit(
                    store,
                    actor_user_id=None,
                    action=f"call.{call.error_code}",
                    entity_type="outbound_call",
                    entity_id=call.id,
                    source_call_id=None,
                )
        logger.warning("scheduler.dispatch_needs_attention", call_id=entity_id, known_failure=known_failure)
        return {"status": "failed" if known_failure else "delivery_unknown"}
    async with application_store(settings) as store:
        call = store.outbound_calls[call_id]
        if call.provider_call_id not in {None, placed.provider_call_id}:
            raise ValueError("Conflicting provider identifier")
        call.provider_call_id = placed.provider_call_id
        # A callback may already have recorded a final outcome; never regress it.
        call.updated_at = ctx.get("now") or utc_now()
        write_audit(
            store,
            actor_user_id=None,
            action="call.provider_accepted",
            entity_type="outbound_call",
            entity_id=call.id,
            source_call_id=None,
        )
    return {"status": "submitted", "provider_call_id": placed.provider_call_id}


# Compatibility for old Redis jobs: regenerate the outbox, never treat a reminder
# or medication-plan ID as a call ID. A fresh tick schedules canonical call jobs.
async def generic_outbound_reminder(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, int]:
    return await scheduler_tick(ctx)


create_recurring_medication_dose = generic_outbound_reminder
medication_reminder_call = generic_outbound_reminder
medication_no_answer_retry = generic_outbound_reminder
low_stock_notification = generic_outbound_reminder
safety_reminder_call = generic_outbound_reminder
safety_retry = generic_outbound_reminder
safety_escalation = generic_outbound_reminder
appointment_reminder_call = generic_outbound_reminder
appointment_followup_call = generic_outbound_reminder
family_notification = generic_outbound_reminder
