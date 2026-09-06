"""No-answer chains use recorded outcomes, not speech or provider acceptance."""

from datetime import time, timedelta

import pytest

from app.domain.enums import MedicationDoseStatus, OutboundCallPurpose, OutboundCallStatus, ReminderStatus, ReminderType
from app.repositories.memory import MemoryStore
from app.schemas import MedicationDoseRecord, MedicationPlanRecord, OutboundCallRecord, ReminderRecord
from app.services.family_directory import FamilyDirectory
from app.services.family_escalation import FamilyEscalationService
from app.utils.datetime import utc_now


def setup_chain(store: MemoryStore) -> tuple[ReminderRecord, list[OutboundCallRecord]]:
    mama = FamilyDirectory(store).by_name("Mama")
    now = utc_now()
    reminder = ReminderRecord(
        requester_user_id=mama.id,
        target_user_id=mama.id,
        reminder_type=ReminderType.HOUSEHOLD_SAFETY,
        message="makni čajnik s plina",
        scheduled_for=now,
        idempotency_key="tea",
        created_at=now,
        updated_at=now,
    )
    store.reminders[reminder.id] = reminder
    calls = []
    for attempt in (1, 2):
        call = OutboundCallRecord(
            target_user_id=mama.id,
            scheduled_for=now - timedelta(minutes=attempt),
            purpose=OutboundCallPurpose.HOUSEHOLD_SAFETY,
            message=reminder.message,
            related_entity_type="reminder",
            related_entity_id=reminder.id,
            status=OutboundCallStatus.NO_ANSWER,
            attempt_number=attempt,
            idempotency_key=f"tea-{attempt}",
            created_at=now,
            updated_at=now,
        )
        store.outbound_calls[call.id] = call
        calls.append(call)
    return reminder, calls


def test_branko_then_natasa_once(store: MemoryStore) -> None:
    reminder, calls = setup_chain(store)
    directory = FamilyDirectory(store)
    contacts = [directory.by_name(name).id for name in ("Branko", "Nataša")]
    service = FamilyEscalationService(store)
    first = service.after_no_answer(calls[-1].id, contact_ids=contacts)
    assert first is not None and first.target_user_id == contacts[0]
    assert "čajnik" in first.message and "Nema odgovora" in first.message
    assert service.after_no_answer(calls[-1].id, contact_ids=contacts) == first
    first.status = OutboundCallStatus.NO_ANSWER
    second = service.after_no_answer(first.id, contact_ids=contacts)
    assert second is not None and second.target_user_id == contacts[1]
    assert service.after_no_answer(first.id, contact_ids=contacts) == second
    second.status = OutboundCallStatus.NO_ANSWER
    assert service.after_no_answer(second.id, contact_ids=contacts) is None
    assert len(store.outbound_calls) == 4
    assert reminder.status == ReminderStatus.SCHEDULED


@pytest.mark.parametrize("status", [OutboundCallStatus.FAILED, OutboundCallStatus.ANSWERED])
def test_no_escalation_for_failure_or_answer(store: MemoryStore, status: OutboundCallStatus) -> None:
    _, calls = setup_chain(store)
    calls[-1].status = status
    branko = FamilyDirectory(store).by_name("Branko")
    assert FamilyEscalationService(store).after_no_answer(calls[-1].id, contact_ids=[branko.id]) is None


def test_completed_reminder_stops_chain(store: MemoryStore) -> None:
    reminder, calls = setup_chain(store)
    reminder.status = ReminderStatus.COMPLETED
    branko = FamilyDirectory(store).by_name("Branko")
    assert FamilyEscalationService(store).after_no_answer(calls[-1].id, contact_ids=[branko.id]) is None


def test_one_missed_call_is_not_enough(store: MemoryStore) -> None:
    _, calls = setup_chain(store)
    del store.outbound_calls[calls[0].id]
    branko = FamilyDirectory(store).by_name("Branko")
    assert FamilyEscalationService(store).after_no_answer(calls[-1].id, contact_ids=[branko.id]) is None


def test_medication_chain_does_not_change_inventory(store: MemoryStore) -> None:
    reminder, calls = setup_chain(store)
    now = utc_now()
    plan = MedicationPlanRecord(
        user_id=reminder.target_user_id,
        display_name="Test",
        schedule_rule="FREQ=DAILY",
        local_schedule_time=time(9),
        current_inventory=10,
        created_at=now,
        updated_at=now,
    )
    dose = MedicationDoseRecord(
        medication_plan_id=plan.id,
        user_id=plan.user_id,
        scheduled_for=now,
        status=MedicationDoseStatus.NO_ANSWER,
        created_at=now,
        updated_at=now,
    )
    store.medication_plans[plan.id] = plan
    store.medication_doses[dose.id] = dose
    for call in calls:
        call.related_entity_type = "medication_dose"
        call.related_entity_id = dose.id
        call.purpose = OutboundCallPurpose.MEDICATION_DOSE
    service = FamilyEscalationService(store)
    first = service.after_no_answer(calls[-1].id)
    assert first is not None
    assert first.target_user_id == FamilyDirectory(store).by_name("Branko").id
    assert "tableta Test" in first.message
    assert plan.current_inventory == 10 and not store.inventory_events
    first.status = OutboundCallStatus.NO_ANSWER
    dose.status = MedicationDoseStatus.USER_REPORTED_TAKEN
    assert service.after_no_answer(first.id) is None


def test_answered_branko_does_not_call_natasa(store: MemoryStore) -> None:
    _, calls = setup_chain(store)
    service = FamilyEscalationService(store)
    first = service.after_no_answer(calls[-1].id)
    assert first is not None
    first.status = OutboundCallStatus.ANSWERED
    assert service.after_no_answer(calls[-1].id) == first
    assert len(store.outbound_calls) == 3
