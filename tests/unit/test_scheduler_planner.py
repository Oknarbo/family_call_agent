"""Deterministic time, recurrence, cancellation and notification planning."""

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.domain.enums import (
    AppointmentStatus,
    DeliveryStatus,
    MedicationInventoryEventType,
    OutboundCallPurpose,
    OutboundCallStatus,
    ReminderStatus,
    ReminderType,
)
from app.domain.exceptions import ValidationError
from app.repositories.memory import MemoryStore
from app.scheduler.planner import SchedulerPlanner
from app.scheduler.recurrence import occurrences
from app.schemas import AppointmentRecord, MedicationPlanRecord, ReminderRecord
from app.services.call_outcomes import CallOutcomeService
from app.services.family_directory import FamilyDirectory
from app.services.medication_inventory import MedicationInventoryService

NOW = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)


def reminder(store: MemoryStore, **overrides: object) -> ReminderRecord:
    mama = FamilyDirectory(store).by_name("Mama")
    values = dict(
        requester_user_id=mama.id,
        target_user_id=mama.id,
        reminder_type=ReminderType.GENERAL,
        message="Test",
        scheduled_for=NOW,
        recurrence_rule=None,
        idempotency_key=str(uuid4()),
        created_at=NOW - timedelta(days=10),
        updated_at=NOW - timedelta(days=10),
    )
    values.update(overrides)
    r = ReminderRecord.model_validate(values)
    store.reminders[r.id] = r
    return r


def plan(store: MemoryStore, **overrides: object) -> MedicationPlanRecord:
    values = dict(
        user_id=FamilyDirectory(store).by_name("Mama").id,
        display_name="Test",
        schedule_rule="FREQ=DAILY",
        local_schedule_time=time(12),
        current_inventory=10,
        created_at=NOW - timedelta(days=10),
        updated_at=NOW - timedelta(days=10),
    )
    values.update(overrides)
    p = MedicationPlanRecord.model_validate(values)
    store.medication_plans[p.id] = p
    return p


@pytest.mark.parametrize(("day", "hour", "minute"), [("2026-03-29", 3, 30), ("2026-10-25", 2, 30)])
def test_dst_one_local_occurrence(day: str, hour: int, minute: int) -> None:
    start = datetime.fromisoformat(day).replace(tzinfo=UTC)
    dates = list(occurrences("FREQ=DAILY", time(2, 30), "Europe/Zagreb", start=start, end=start + timedelta(hours=23)))
    assert len(dates) == 1
    local = dates[0].astimezone(ZoneInfo("Europe/Zagreb"))
    assert (local.hour, local.minute) == (hour, minute)


def test_weekly_and_invalid_rule() -> None:
    dates = list(
        occurrences("FREQ=WEEKLY;BYDAY=MO;BYHOUR=12", time(9), "Europe/Zagreb", start=NOW, end=NOW + timedelta(days=7))
    )
    assert len(dates) == 1 and dates[0].weekday() == 0 and dates[0].hour == 10
    with pytest.raises(ValidationError):
        list(occurrences("FREQ=MINUTELY", time(9), "Europe/Zagreb", start=NOW, end=NOW))


def test_daily_reminder_has_distinct_occurrences_without_backlog(store: MemoryStore, settings: Settings) -> None:
    r = reminder(store, recurrence_rule="FREQ=DAILY", scheduled_for=NOW - timedelta(days=9))
    planner = SchedulerPlanner(store, settings)
    calls = planner.materialize(NOW)
    assert len(calls) == 1 and calls[0].occurrence_for == NOW
    assert planner.materialize(NOW)[0].id == calls[0].id
    calls[0].status = OutboundCallStatus.COMPLETED
    tomorrow = planner.materialize(NOW + timedelta(days=1))
    assert len(tomorrow) == 1 and tomorrow[0].id != calls[0].id
    assert r.status == ReminderStatus.SCHEDULED


def test_old_queued_recurring_call_cannot_dispatch(store: MemoryStore, settings: Settings) -> None:
    reminder(store, recurrence_rule="FREQ=DAILY")
    planner = SchedulerPlanner(store, settings)
    old = planner.materialize(NOW)[0]
    assert not planner.dispatchable(old, NOW + timedelta(days=2))


def test_appointment_reschedule_and_cancel_invalidate_old_queue(store: MemoryStore, settings: Settings) -> None:
    mama = FamilyDirectory(store).by_name("Mama")
    a = AppointmentRecord(
        patient_user_id=mama.id,
        created_by_user_id=mama.id,
        provider_name="Horvat",
        scheduled_for=NOW + timedelta(hours=2),
        reminder_offsets_minutes=[120],
        idempotency_key="appt",
        created_at=NOW - timedelta(days=1),
        updated_at=NOW,
    )
    store.appointments[a.id] = a
    planner = SchedulerPlanner(store, settings)
    old = planner.materialize(NOW)[0]
    a.scheduled_for += timedelta(minutes=30)
    calls = planner.materialize(NOW)
    assert old.status == OutboundCallStatus.CANCELLED
    assert len(calls) == 1 and calls[0].scheduled_for == NOW + timedelta(minutes=30)
    a.status = AppointmentStatus.CANCELLED
    assert planner.materialize(NOW) == []


def test_no_old_medication_catchup_and_no_inventory_change(store: MemoryStore, settings: Settings) -> None:
    p = plan(store, local_schedule_time=time(8))
    planner = SchedulerPlanner(store, settings)
    assert planner.materialize(NOW) == []  # Noon local: four hours too late.
    assert not store.medication_doses and p.current_inventory == 10


def test_medication_materialization_is_idempotent_and_plan_change_cancels(
    store: MemoryStore, settings: Settings
) -> None:
    p = plan(store, schedule_rule="FREQ=DAILY;BYHOUR=12;BYMINUTE=0")
    planner = SchedulerPlanner(store, settings)
    first = planner.materialize(NOW)[0]
    assert planner.materialize(NOW)[0].id == first.id
    assert len(store.medication_doses) == 1
    p.local_schedule_time = time(12, 30)
    future = planner.materialize(NOW)
    assert first.status == OutboundCallStatus.CANCELLED
    assert len(future) == 1 and future[0].scheduled_for == NOW + timedelta(minutes=30)
    assert p.current_inventory == 10


def test_inactive_family_member_is_not_called(store: MemoryStore, settings: Settings) -> None:
    r = reminder(store)
    store.family_members[r.target_user_id].is_active = False
    assert SchedulerPlanner(store, settings).materialize(NOW) == []


def test_low_stock_notifies_once_until_refilled(store: MemoryStore, settings: Settings) -> None:
    p = plan(store, current_inventory=2, low_stock_threshold=5)
    planner = SchedulerPlanner(store, settings)
    planner.materialize(NOW)
    assert len(store.notifications) == 1
    notice = next(iter(store.notifications.values()))
    assert "doktoricom" in notice.message
    notice.delivery_status = DeliveryStatus.SENT
    planner.materialize(NOW + timedelta(minutes=1))
    assert len(store.notifications) == 1
    inventory = MedicationInventoryService(store)
    for quantity, key in [(20, "refill"), (5, "low-again")]:
        inventory.change(
            requester_user_id=p.user_id,
            medication_plan_id=p.id,
            event_type=MedicationInventoryEventType.MANUAL_CORRECTION,
            absolute_quantity=quantity,
            reason="test",
            source_call_id="test",
            idempotency_key=key,
        )
    planner.materialize(NOW + timedelta(minutes=2))
    assert len(store.notifications) == 2


def test_safety_confirmed_occurrence_cancels_retry_but_not_tomorrow(store: MemoryStore, settings: Settings) -> None:
    reminder(store, recurrence_rule="FREQ=DAILY", reminder_type=ReminderType.HOUSEHOLD_SAFETY)
    planner = SchedulerPlanner(store, settings)
    first = planner.materialize(NOW)[0]
    first.status = OutboundCallStatus.ANSWERED
    service = CallOutcomeService(store, settings)
    retry = service.retry(first, 2, NOW)
    service.record_response(first.id, "completed", now=NOW)
    assert retry.status == OutboundCallStatus.CANCELLED
    tomorrow = planner.materialize(NOW + timedelta(days=1))
    assert len(tomorrow) == 1
    assert tomorrow[0].purpose == OutboundCallPurpose.HOUSEHOLD_SAFETY
