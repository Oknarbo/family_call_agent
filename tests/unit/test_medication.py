"""Medication self-reporting and inventory invariants."""

from datetime import UTC, datetime, time, timedelta

import pytest

from app.domain.enums import MedicationDoseStatus, MedicationInventoryEventType
from app.domain.exceptions import DuplicateActionError, InventoryWouldBeNegativeError
from app.repositories.memory import MemoryStore
from app.schemas import FamilyMemberRecord
from app.services.medication_inventory import MedicationInventoryService
from app.services.medication_plans import MedicationPlanService


def _plan(store: MemoryStore, mama: FamilyMemberRecord, inventory: int = 3):
    return MedicationPlanService(store).create_plan(
        requester_user_id=mama.id,
        target_user_id=mama.id,
        medication_display_name="tableta u 12",
        schedule_rule="FREQ=DAILY;BYHOUR=12;BYMINUTE=0",
        local_schedule_time=time(12),
        dose_quantity=1,
        initial_inventory=inventory,
        low_stock_threshold=2,
        escalation_contact_user_id=None,
        source_call_id="call-plan",
        idempotency_key="plan-1",
    )


def test_initial_inventory_creates_auditable_event(store: MemoryStore, mama: FamilyMemberRecord) -> None:
    plan = _plan(store, mama, 30)
    event = next(iter(store.inventory_events.values()))
    assert plan.current_inventory == 30
    assert event.event_type == MedicationInventoryEventType.INITIAL_STOCK
    assert event.previous_quantity == 0 and event.new_quantity == 30


def test_confirmed_dose_decrements_exactly_once(store: MemoryStore, mama: FamilyMemberRecord) -> None:
    service = MedicationPlanService(store)
    plan = _plan(store, mama)
    dose = service.create_dose(plan.id, datetime.now(UTC) + timedelta(hours=1), "dose-create")
    service.record_response(
        user_id=mama.id,
        medication_plan_id=plan.id,
        scheduled_dose_event_id=dose.id,
        reported_status=MedicationDoseStatus.USER_REPORTED_TAKEN,
        reported_quantity=1,
        reported_at=datetime.now(UTC),
        source_call_id="call-dose",
        idempotency_key="response-1",
    )
    assert plan.current_inventory == 2
    service.record_response(
        user_id=mama.id,
        medication_plan_id=plan.id,
        scheduled_dose_event_id=dose.id,
        reported_status=MedicationDoseStatus.USER_REPORTED_TAKEN,
        reported_quantity=1,
        reported_at=datetime.now(UTC),
        source_call_id="call-dose",
        idempotency_key="response-1",
    )
    assert plan.current_inventory == 2
    with pytest.raises(DuplicateActionError):
        service.record_response(
            user_id=mama.id,
            medication_plan_id=plan.id,
            scheduled_dose_event_id=dose.id,
            reported_status=MedicationDoseStatus.USER_REPORTED_TAKEN,
            reported_quantity=1,
            reported_at=datetime.now(UTC),
            source_call_id="call-dose",
            idempotency_key="different-response-key",
        )


@pytest.mark.parametrize(
    "status",
    [
        MedicationDoseStatus.NO_ANSWER,
        MedicationDoseStatus.USER_REPORTED_NOT_TAKEN,
        MedicationDoseStatus.UNCLEAR_RESPONSE,
        MedicationDoseStatus.CALL_LATER_REQUESTED,
    ],
)
def test_non_confirmations_never_decrement(
    store: MemoryStore, mama: FamilyMemberRecord, status: MedicationDoseStatus
) -> None:
    service = MedicationPlanService(store)
    plan = _plan(store, mama)
    dose = service.create_dose(plan.id, datetime.now(UTC) + timedelta(hours=1), f"dose-{status}")
    service.record_response(
        user_id=mama.id,
        medication_plan_id=plan.id,
        scheduled_dose_event_id=dose.id,
        reported_status=status,
        reported_quantity=None,
        reported_at=datetime.now(UTC),
        source_call_id="call",
        idempotency_key=f"response-{status}",
    )
    assert plan.current_inventory == 3


def test_add_set_negative_prevention_and_low_stock(store: MemoryStore, mama: FamilyMemberRecord) -> None:
    plan = _plan(store, mama)
    inventory = MedicationInventoryService(store)
    added = inventory.change(
        requester_user_id=mama.id,
        medication_plan_id=plan.id,
        event_type=MedicationInventoryEventType.BOX_ADDED,
        quantity_delta=20,
        reason="Nova kutija",
        source_call_id="box",
        idempotency_key="box-1",
    )
    assert added.new_quantity == 23
    corrected = inventory.change(
        requester_user_id=mama.id,
        medication_plan_id=plan.id,
        event_type=MedicationInventoryEventType.MANUAL_CORRECTION,
        absolute_quantity=2,
        reason="Ručno prebrojano",
        source_call_id="correction",
        idempotency_key="set-2",
    )
    assert corrected.previous_quantity == 23 and corrected.new_quantity == 2
    assert MedicationPlanService(store).is_low_stock(plan.id)
    with pytest.raises(InventoryWouldBeNegativeError):
        inventory.change(
            requester_user_id=mama.id,
            medication_plan_id=plan.id,
            event_type=MedicationInventoryEventType.MANUAL_CORRECTION,
            quantity_delta=-3,
            reason="Nemoguće",
            source_call_id="bad",
            idempotency_key="negative",
        )


def test_reversal_restores_inventory(store: MemoryStore, mama: FamilyMemberRecord) -> None:
    service = MedicationPlanService(store)
    plan = _plan(store, mama)
    dose = service.create_dose(plan.id, datetime.now(UTC) + timedelta(hours=1), "dose-reverse")
    service.record_response(
        user_id=mama.id,
        medication_plan_id=plan.id,
        scheduled_dose_event_id=dose.id,
        reported_status=MedicationDoseStatus.USER_REPORTED_TAKEN,
        reported_quantity=1,
        reported_at=datetime.now(UTC),
        source_call_id="call",
        idempotency_key="taken-reverse",
    )
    service.reverse_confirmation(
        requester_user_id=mama.id,
        medication_dose_event_id=dose.id,
        reason="Korisnica je ispravila jučerašnji odgovor",
        source_call_id="correction",
        idempotency_key="reverse-1",
    )
    assert plan.current_inventory == 3
