"""Provider outcomes and explicit user responses drive durable follow-up work."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.config import Settings
from app.domain.enums import (
    DeliveryStatus,
    MedicationDoseStatus,
    OutboundCallPurpose,
    OutboundCallStatus,
    ReminderStatus,
)
from app.domain.exceptions import NotFoundError, ValidationError
from app.repositories.protocols import Store
from app.scheduler.planner import SchedulerPlanner
from app.schemas import OutboundCallRecord
from app.services.audit import write_audit
from app.services.family_escalation import FamilyEscalationService
from app.services.medication_plans import MedicationPlanService

TERMINAL = {
    OutboundCallStatus.COMPLETED,
    OutboundCallStatus.NO_ANSWER,
    OutboundCallStatus.BUSY,
    OutboundCallStatus.FAILED,
    OutboundCallStatus.CANCELLED,
}


class CallOutcomeService:
    def __init__(self, store: Store, settings: Settings) -> None:
        self.store, self.settings = store, settings
        self.planner = SchedulerPlanner(store, settings)

    def record_status(self, call_id: UUID, provider_call_id: str, status: OutboundCallStatus, *, now: datetime) -> None:
        call = self._get(call_id)
        if not provider_call_id or (call.provider_call_id and call.provider_call_id != provider_call_id):
            raise ValidationError("Provider call ID mismatch")
        if status not in TERMINAL | {OutboundCallStatus.RINGING, OutboundCallStatus.ANSWERED}:
            raise ValidationError("Unsupported provider outcome")
        if call.status == OutboundCallStatus.SCHEDULED:
            raise ValidationError("Call has not been dispatched")
        if call.status in TERMINAL:
            return  # Duplicate or contradictory late terminal callback.
        if call.answered_at is not None and status in {
            OutboundCallStatus.RINGING,
            OutboundCallStatus.NO_ANSWER,
            OutboundCallStatus.BUSY,
        }:
            return
        call.provider_call_id = provider_call_id
        call.status, call.updated_at = status, now
        if call.error_code != "voice_transport_failed":
            call.error_code = None
        if status == OutboundCallStatus.ANSWERED:
            call.answered_at = now
        if status in TERMINAL:
            call.ended_at = now
        self._audit(call, f"call.{status.value}")
        if not self.planner.active(call):
            self.store.save()
            return
        if status == OutboundCallStatus.NO_ANSWER:
            self._no_answer(call, now)
        elif status == OutboundCallStatus.BUSY and call.attempt_number < 2:
            self.retry(call, self.settings.general_retry_minutes, now)
        elif (
            status == OutboundCallStatus.COMPLETED
            and call.user_outcome not in {"call_later", "voice_failed"}
            and (
                self.settings.telephony_provider != "twilio"
                or call.user_outcome in {"message_delivered", "completed", "taken"}
            )
        ):
            if call.purpose == OutboundCallPurpose.GENERAL_REMINDER and call.related_entity_type == "reminder":
                self._complete_reminder(call)
            elif call.related_entity_type == "notification":
                n = self.store.notifications[call.related_entity_id]
                n.delivery_status, n.delivered_at = DeliveryStatus.SENT, now
        self.store.save()

    def _no_answer(self, call: OutboundCallRecord, now: datetime) -> None:
        important = call.purpose in {OutboundCallPurpose.MEDICATION_DOSE, OutboundCallPurpose.HOUSEHOLD_SAFETY}
        family_chain = call.purpose == OutboundCallPurpose.FAMILY_NOTIFICATION and (
            call.related_entity_type in {"reminder", "medication_dose"}
        )
        medication = call.related_entity_type == "medication_dose"
        limit = (
            self.settings.medication_no_answer_attempts
            if medication
            else self.settings.safety_escalate_after_no_answers
        )
        if family_chain:
            FamilyEscalationService(self.store).after_no_answer(call.id, patient_attempts=limit, now=now)
            return
        if medication:
            self.store.medication_doses[call.related_entity_id].status = MedicationDoseStatus.NO_ANSWER
        missed = sum(
            c.status == OutboundCallStatus.NO_ANSWER
            for c in self.store.outbound_calls.values()
            if c.related_entity_type == call.related_entity_type
            and c.related_entity_id == call.related_entity_id
            and c.occurrence_for == call.occurrence_for
            and c.target_user_id == call.target_user_id
        )
        if important and missed >= limit:
            FamilyEscalationService(self.store).after_no_answer(call.id, patient_attempts=limit, now=now)
        elif call.attempt_number < (
            self.settings.max_user_call_attempts if important else self.settings.general_no_answer_attempts
        ):
            delay = self.settings.general_retry_minutes
            if medication:
                delay = self.settings.medication_retry_minutes
            elif important:
                delays = self.settings.safety_retry_delays_minutes
                delay = delays[min(missed - 1, len(delays) - 1)] if delays else 2
            self.retry(call, delay, now)

    def retry(self, call: OutboundCallRecord, delay_minutes: int, now: datetime) -> OutboundCallRecord:
        if delay_minutes <= 0 or delay_minutes > 1440:
            raise ValidationError("Invalid follow-up delay")
        key = f"retry:{call.id}"
        if key in self.store.idempotency:
            return self.store.outbound_calls[self.store.idempotency[key]]
        result = call.model_copy(
            update={
                "id": uuid4(),
                "status": OutboundCallStatus.SCHEDULED,
                "scheduled_for": now + timedelta(minutes=delay_minutes),
                "attempt_number": call.attempt_number + 1,
                "provider_call_id": None,
                "started_at": None,
                "answered_at": None,
                "ended_at": None,
                "user_outcome": None,
                "error_code": None,
                "idempotency_key": key,
                "created_at": now,
                "updated_at": now,
            }
        )
        self.store.outbound_calls[result.id], self.store.idempotency[key] = result, result.id
        self._audit(result, "call.retry_scheduled")
        return result

    def record_response(self, call_id: UUID, outcome: str, *, now: datetime, delay_minutes: int | None = None) -> None:
        """Transport must authenticate and associate the response with this call.

        No language classification here: only explicitly validated outcomes enter.
        """
        call = self._get(call_id)
        if outcome not in {"completed", "taken", "not_taken", "unclear", "call_later"}:
            raise ValidationError("Unsupported user response")
        if call.status not in {OutboundCallStatus.ANSWERED, OutboundCallStatus.COMPLETED}:
            raise ValidationError("Response requires an answered call")
        if call.user_outcome == outcome or call.user_outcome in {"completed", "taken", "call_later"}:
            return
        if outcome == "call_later" and (
            delay_minutes is None
            or not 1 <= delay_minutes <= 1440
            or call.attempt_number >= self.settings.max_user_call_attempts
        ):
            raise ValidationError("Follow-up delay or attempt limit is invalid")
        active = self.planner.active(call)
        if call.related_entity_type == "medication_dose" and call.user_outcome in {"unclear", "not_taken"}:
            dose = self.store.medication_doses[call.related_entity_id]
            plan = self.store.medication_plans[dose.medication_plan_id]
            active = plan.is_active and dose.status in {
                MedicationDoseStatus.UNCLEAR_RESPONSE,
                MedicationDoseStatus.USER_REPORTED_NOT_TAKEN,
            }
            member = self.store.family_members.get(call.target_user_id)
            active = active and member is not None and member.is_active
            active = active and (
                not call.source_version
                or call.source_version == self.planner.version(call.related_entity_type, call.related_entity_id)
            )
        if not active:
            return
        if call.related_entity_type == "medication_dose" and call.purpose == OutboundCallPurpose.MEDICATION_DOSE:
            if outcome == "completed":
                raise ValidationError("Medication requires an explicit taken outcome")
            statuses = {
                "taken": MedicationDoseStatus.USER_REPORTED_TAKEN,
                "not_taken": MedicationDoseStatus.USER_REPORTED_NOT_TAKEN,
                "unclear": MedicationDoseStatus.UNCLEAR_RESPONSE,
                "call_later": MedicationDoseStatus.CALL_LATER_REQUESTED,
            }
            d = self.store.medication_doses[call.related_entity_id]
            MedicationPlanService(self.store).record_response(
                user_id=d.user_id,
                medication_plan_id=d.medication_plan_id,
                scheduled_dose_event_id=d.id,
                reported_status=statuses[outcome],
                reported_quantity=None,
                reported_at=now,
                source_call_id=str(call.id),
                idempotency_key=f"call-response:{call.id}:{outcome}",
            )
        elif outcome == "taken":
            raise ValidationError("Only a medication call can confirm medication")
        elif (
            outcome == "completed"
            and call.related_entity_type == "reminder"
            and (call.purpose != OutboundCallPurpose.FAMILY_NOTIFICATION)
        ):
            self._complete_reminder(call)
        if outcome == "call_later" and delay_minutes is not None:
            self.retry(call, delay_minutes, now)
        call.user_outcome, call.updated_at = outcome, now
        self._audit(call, f"call.user_{outcome}")
        # Cancel queued duplicates/retries immediately on confirmed completion.
        for pending in self.store.outbound_calls.values():
            if pending.status == OutboundCallStatus.SCHEDULED and not self.planner.active(pending):
                pending.status = OutboundCallStatus.CANCELLED
        self.store.save()

    def _complete_reminder(self, call: OutboundCallRecord) -> None:
        r = self.store.reminders[call.related_entity_id]
        if not r.recurrence_rule:
            r.status = ReminderStatus.COMPLETED

    def _get(self, call_id: UUID) -> OutboundCallRecord:
        try:
            return self.store.outbound_calls[call_id]
        except KeyError as exc:
            raise NotFoundError from exc

    def _audit(self, call: OutboundCallRecord, action: str) -> None:
        write_audit(
            self.store,
            actor_user_id=None,
            action=action,
            entity_type="outbound_call",
            entity_id=call.id,
            source_call_id=None,
        )
