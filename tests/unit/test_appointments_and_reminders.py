"""Appointment, reminder and safety service behavior."""

from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.domain.enums import AppointmentStatus, ReminderStatus, ReminderType, SafetyReminderOutcome
from app.domain.exceptions import SchedulingInPastError
from app.repositories.memory import MemoryStore
from app.schemas import FamilyMemberRecord
from app.services.appointments import AppointmentService
from app.services.household_safety import HouseholdSafetyService
from app.services.reminders import ReminderService


def test_reminder_is_idempotent_and_cross_family_logged(store: MemoryStore, mama: FamilyMemberRecord) -> None:
    tata = next(member for member in store.family_members.values() if member.display_name == "Tata")
    service = ReminderService(store)
    values = dict(
        requester_user_id=mama.id,
        target_user_id=tata.id,
        message="da nazove ambulantu",
        scheduled_for=datetime.now(UTC) + timedelta(hours=1),
        reminder_type=ReminderType.GENERAL,
        reminder_subtype=None,
        recurrence_rule=None,
        source_call_id="cross-family",
        idempotency_key="reminder-idempotent",
    )
    first = service.schedule(**values)
    second = service.schedule(**values)
    assert first.id == second.id
    assert len(store.reminders) == 1
    assert any(audit.action == "reminder.scheduled" for audit in store.audits.values())


def test_past_reminder_is_rejected(store: MemoryStore, mama: FamilyMemberRecord) -> None:
    with pytest.raises(SchedulingInPastError):
        ReminderService(store).schedule(
            requester_user_id=mama.id,
            target_user_id=mama.id,
            message="prošlo",
            scheduled_for=datetime.now(UTC) - timedelta(minutes=1),
            reminder_type=ReminderType.GENERAL,
            reminder_subtype=None,
            recurrence_rule=None,
            source_call_id="past",
            idempotency_key="past",
        )


def test_cancel_reminder(store: MemoryStore, mama: FamilyMemberRecord) -> None:
    service = ReminderService(store)
    reminder = service.schedule(
        requester_user_id=mama.id,
        target_user_id=mama.id,
        message="kupi kruh",
        scheduled_for=datetime.now(UTC) + timedelta(hours=1),
        reminder_type=ReminderType.GENERAL,
        reminder_subtype=None,
        recurrence_rule=None,
        source_call_id="create",
        idempotency_key="cancel-me",
    )
    service.cancel(mama.id, reminder.id, "cancel")
    assert reminder.status == ReminderStatus.CANCELLED


def test_appointment_default_reminders_and_no_attendance_inference(
    store: MemoryStore, mama: FamilyMemberRecord
) -> None:
    service = AppointmentService(store)
    appointment = service.create(
        requester_user_id=mama.id,
        patient_user_id=mama.id,
        provider_name="doktorica Horvat",
        appointment_type="kontrola",
        location="ambulanta",
        scheduled_for=datetime.now(UTC) + timedelta(days=5),
        reminder_offsets_minutes=[],
        notify_user_ids=[],
        source_call_id="appointment",
        idempotency_key="appointment-1",
    )
    assert appointment.reminder_offsets_minutes == [1440, 120]
    assert appointment.status == AppointmentStatus.SCHEDULED
    appointment.scheduled_for = datetime.now(UTC) - timedelta(days=1)
    assert appointment.status == AppointmentStatus.SCHEDULED


def test_appointment_reschedule_cancel_and_query(store: MemoryStore, mama: FamilyMemberRecord) -> None:
    service = AppointmentService(store)
    appointment = service.create(
        requester_user_id=mama.id,
        patient_user_id=mama.id,
        provider_name="doktorica Horvat",
        appointment_type=None,
        location=None,
        scheduled_for=datetime.now(UTC) + timedelta(days=5),
        reminder_offsets_minutes=[1440, 120],
        notify_user_ids=[],
        source_call_id="appointment",
        idempotency_key="appointment-2",
    )
    service.update(
        requester_user_id=mama.id,
        appointment_id=appointment.id,
        scheduled_for=datetime.now(UTC) + timedelta(days=7),
        source_call_id="reschedule",
    )
    assert appointment.status == AppointmentStatus.RESCHEDULED
    assert service.upcoming(mama.id, mama.id)[0].id == appointment.id
    service.cancel(mama.id, appointment.id, "cancel")
    assert appointment.status == AppointmentStatus.CANCELLED
    assert service.upcoming(mama.id, mama.id) == []


def test_household_safety_retry_and_escalation(store: MemoryStore, mama: FamilyMemberRecord) -> None:
    service = HouseholdSafetyService(
        store,
        Settings(
            app_env="test",
            safety_retry_delays_minutes=[2, 3],
            safety_escalate_after_no_answers=2,
        ),
    )
    reminder = service.schedule(
        requester_user_id=mama.id,
        target_user_id=mama.id,
        message="makni čaj s plamenika",
        scheduled_for=datetime.now(UTC) + timedelta(minutes=15),
        subtype="tea",
        source_call_id="tea",
        idempotency_key="tea-1",
    )
    assert reminder.reminder_type == ReminderType.HOUSEHOLD_SAFETY
    assert reminder.priority == 10
    assert service.next_action(SafetyReminderOutcome.NO_ANSWER, 1) == "retry"
    assert service.next_action(SafetyReminderOutcome.NO_ANSWER, 2) == "escalate"
    assert service.next_action(SafetyReminderOutcome.COMPLETED, 1) == "complete"
