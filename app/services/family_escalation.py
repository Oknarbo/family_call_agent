"""Prepare family calls after confirmed no-answer outcomes; never place calls here."""

from datetime import datetime, timedelta
from uuid import UUID

from app.domain.enums import MedicationDoseStatus, OutboundCallPurpose, OutboundCallStatus, ReminderStatus, ReminderType
from app.domain.exceptions import NotFoundError
from app.repositories.protocols import Store
from app.schemas import OutboundCallRecord
from app.services.audit import write_audit
from app.utils.datetime import utc_now


class FamilyEscalationService:
    """One chain per reminder/dose: patient retries, then ordered family contacts.

    The scheduler must persist actual provider outcomes before invoking this
    service. Empty speech and provider failures are not evidence of no answer.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    def after_no_answer(
        self,
        call_id: UUID,
        *,
        contact_ids: list[UUID] | None = None,
        patient_attempts: int = 2,
        now: datetime | None = None,
    ) -> OutboundCallRecord | None:
        if patient_attempts < 1:
            raise ValueError("patient_attempts must be positive")
        now = now or utc_now()
        try:
            trigger = self.store.outbound_calls[call_id]
        except KeyError as exc:
            raise NotFoundError from exc
        if trigger.status != OutboundCallStatus.NO_ANSWER:
            return None
        kind, entity_id = trigger.related_entity_type, trigger.related_entity_id
        if kind == "reminder":
            reminder = self.store.reminders.get(entity_id)
            if (
                reminder is None
                or reminder.reminder_type != ReminderType.HOUSEHOLD_SAFETY
                or reminder.status not in {ReminderStatus.SCHEDULED, ReminderStatus.EXECUTING}
            ):
                return None
            patient_id, description = reminder.target_user_id, reminder.message
        elif kind == "medication_dose":
            dose = self.store.medication_doses.get(entity_id)
            if dose is None or dose.status not in {
                MedicationDoseStatus.SCHEDULED,
                MedicationDoseStatus.REMINDER_STARTED,
                MedicationDoseStatus.NO_ANSWER,
            }:
                return None
            plan = self.store.medication_plans.get(dose.medication_plan_id)
            if plan is None or not plan.is_active:
                return None
            patient_id, description = dose.user_id, f"tableta {plan.display_name}"
        else:
            return None

        patient = self.store.family_members.get(patient_id)
        if patient is None or not patient.is_active:
            return None
        if contact_ids is None:
            configured = patient.escalation_preferences.get("important_no_answer_contact_ids")
            if configured is not None:
                contact_ids = [UUID(value) for value in configured]
            else:
                # Backward-compatible defaults for already saved family records.
                contact_ids = [
                    member.id
                    for role in ("branko", "natasa")
                    for member in self.store.family_members.values()
                    if member.role.value == role
                ]
        related = [
            call
            for call in self.store.outbound_calls.values()
            if call.related_entity_type == kind
            and call.related_entity_id == entity_id
            and call.occurrence_for == trigger.occurrence_for
        ]
        patient_calls = [call for call in related if call.target_user_id == patient_id]
        if sum(call.status == OutboundCallStatus.NO_ANSWER for call in patient_calls) < patient_attempts:
            return None
        if any(
            call.status not in {OutboundCallStatus.NO_ANSWER, OutboundCallStatus.BUSY, OutboundCallStatus.FAILED}
            and call.user_outcome != "call_later"
            for call in patient_calls
        ):
            return None

        # An answered, pending or failed contact call never advances the chain.
        # Only an explicit no-answer result allows the next family contact.
        for contact_id in dict.fromkeys(contact_ids):
            contact = self.store.family_members.get(contact_id)
            if contact_id == patient_id or contact is None or not contact.is_active:
                continue
            key = f"family-escalation:{kind}:{entity_id}:{contact_id}"
            if trigger.occurrence_for is not None:
                key += f":{trigger.occurrence_for.isoformat()}"
            previous_id = self.store.idempotency.get(key)
            if previous_id is not None:
                previous = self.store.outbound_calls[previous_id]
                if previous.status == OutboundCallStatus.NO_ANSWER:
                    continue
                return previous
            result = OutboundCallRecord(
                target_user_id=contact_id,
                scheduled_for=now + timedelta(seconds=1),
                message=(
                    f"Ovdje Zvonko. Nema odgovora na ponovljene pozive za osobu {patient.display_name}. "
                    f"Podsjetnik: {description}. Molim te provjeri je li sve u redu."
                ),
                purpose=OutboundCallPurpose.FAMILY_NOTIFICATION,
                related_entity_type=kind,
                related_entity_id=entity_id,
                idempotency_key=key,
                occurrence_for=trigger.occurrence_for,
                source_version=trigger.source_version,
                priority=20,
                created_at=now,
                updated_at=now,
            )
            self.store.outbound_calls[result.id] = result
            self.store.idempotency[key] = result.id
            write_audit(
                self.store,
                actor_user_id=None,
                action="family_escalation.scheduled",
                entity_type="outbound_call",
                entity_id=result.id,
                source_call_id=None,
            )
            self.store.save()
            return result
        return None
