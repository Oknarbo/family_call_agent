"""Real SQL migrations, independent connections, atomicity and worker composition."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, MetaData, inspect, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.agent.state import ConversationState
from app.config import Settings
from app.dependencies import application_store
from app.domain.enums import MedicationDoseStatus, OutboundCallPurpose, OutboundCallStatus, ReminderType
from app.domain.exceptions import InventoryWouldBeNegativeError
from app.models import Reminder
from app.repositories.memory import MemoryStore
from app.scheduler.jobs import generic_outbound_reminder
from app.services.appointments import AppointmentService
from app.services.conversation import conversation_turn
from app.services.family_directory import FamilyDirectory
from app.services.family_escalation import FamilyEscalationService
from app.services.medication_plans import MedicationPlanService
from app.services.notifications import NotificationService
from app.services.outbound_calls import OutboundCallService
from app.services.reminders import ReminderService
from app.utils.datetime import utc_now
from scripts.import_development_data import import_data


def migrate(connection: Connection, revision: str = "head") -> None:
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


@pytest.fixture
async def durable_settings(tmp_path: Path) -> AsyncIterator[Settings]:
    settings = Settings(app_env="test", database_url=f"sqlite+aiosqlite:///{tmp_path / 'family.db'}")
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()
    async with application_store(settings) as store:
        FamilyDirectory(store).seed(settings)
    yield settings


def schedule(store: MemoryStore, key: str = "shared") -> UUID:
    mama = FamilyDirectory(store).by_name("Mama")
    return (
        ReminderService(store)
        .schedule(
            requester_user_id=mama.id,
            target_user_id=mama.id,
            message="makni čajnik s plina",
            scheduled_for=utc_now() + timedelta(minutes=15),
            reminder_type=ReminderType.HOUSEHOLD_SAFETY,
            reminder_subtype="tea",
            recurrence_rule=None,
            source_call_id="test",
            idempotency_key=key,
        )
        .id
    )


def medication(store: MemoryStore) -> tuple[UUID, UUID]:
    mama = FamilyDirectory(store).by_name("Mama")
    service = MedicationPlanService(store)
    plan = service.create_plan(
        requester_user_id=mama.id,
        target_user_id=mama.id,
        medication_display_name="Test",
        schedule_rule="FREQ=DAILY",
        local_schedule_time=time(9),
        dose_quantity=1,
        initial_inventory=2,
        low_stock_threshold=1,
        escalation_contact_user_id=None,
        source_call_id="test",
        idempotency_key="plan",
    )
    dose = service.create_dose(plan.id, utc_now(), "dose")
    return plan.id, dose.id


def confirm(store: MemoryStore, plan_id: UUID, dose_id: UUID, quantity: int = 1) -> None:
    MedicationPlanService(store).record_response(
        user_id=store.medication_plans[plan_id].user_id,
        medication_plan_id=plan_id,
        scheduled_dose_event_id=dose_id,
        reported_status=MedicationDoseStatus.USER_REPORTED_TAKEN,
        reported_quantity=quantity,
        reported_at=utc_now(),
        source_call_id="response",
        idempotency_key="response",
    )


async def test_restart_and_idempotency(durable_settings: Settings) -> None:
    async with application_store(durable_settings) as store:
        reminder_id = schedule(store)
    # application_store creates and disposes a separate engine each time.
    async with application_store(durable_settings) as restarted:
        assert schedule(restarted) == reminder_id
        assert len(restarted.reminders) == 1
        assert restarted.reminders[reminder_id].scheduled_for.tzinfo == UTC
        assert restarted.audits
    engine = create_async_engine(durable_settings.database_url)
    try:
        async with engine.connect() as connection:
            assert (await connection.execute(select(Reminder.message))).scalar_one() == "makni čajnik s plina"
    finally:
        await engine.dispose()


async def test_medication_failure_rolls_back_everything(durable_settings: Settings) -> None:
    async with application_store(durable_settings) as store:
        plan_id, dose_id = medication(store)
    with pytest.raises(InventoryWouldBeNegativeError):
        async with application_store(durable_settings) as store:
            confirm(store, plan_id, dose_id, quantity=3)
    async with application_store(durable_settings) as store:
        assert store.medication_plans[plan_id].current_inventory == 2
        assert store.medication_doses[dose_id].status == MedicationDoseStatus.SCHEDULED
        assert "response" not in store.idempotency
        confirm(store, plan_id, dose_id)
    async with application_store(durable_settings) as store:
        confirm(store, plan_id, dose_id)
        assert store.medication_plans[plan_id].current_inventory == 1
        assert len(store.inventory_events) == 2  # Initial stock and one deduction.


async def test_concurrent_requests_preserve_both_changes(durable_settings: Settings) -> None:
    async def write(key: str) -> UUID:
        async with application_store(durable_settings) as store:
            return schedule(store, key)

    ids = await asyncio.gather(write("first"), write("second"))
    async with application_store(durable_settings) as store:
        assert set(store.reminders) == set(ids)
    duplicate_ids = await asyncio.gather(write("same"), write("same"))
    assert duplicate_ids[0] == duplicate_ids[1]


async def test_explicit_abort_discards_partial_graph_write(durable_settings: Settings) -> None:
    async with application_store(durable_settings) as store:
        schedule(store)
        store.abort()
    async with application_store(durable_settings) as store:
        assert not store.reminders and not store.idempotency


async def test_appointment_notification_and_escalation_survive_restart(durable_settings: Settings) -> None:
    async with application_store(durable_settings) as store:
        directory = FamilyDirectory(store)
        mama, branko = directory.by_name("Mama"), directory.by_name("Branko")
        appointment = AppointmentService(store).create(
            requester_user_id=mama.id,
            patient_user_id=mama.id,
            provider_name="Horvat",
            appointment_type="kontrola",
            location="ambulanta",
            scheduled_for=utc_now() + timedelta(days=2),
            reminder_offsets_minutes=[60],
            notify_user_ids=[branko.id],
            source_call_id="test",
            idempotency_key="appt",
        )
        notification = NotificationService(store).create(
            requester_user_id=mama.id,
            target_user_id=branko.id,
            message="Test",
            notification_type="family",
            related_entity_type="appointment",
            related_entity_id=appointment.id,
            idempotency_key="notice",
        )
        reminder_id = schedule(store)
        for attempt in (1, 2):
            call = OutboundCallService(store).schedule(
                requester_user_id=mama.id,
                target_user_id=mama.id,
                scheduled_for=utc_now() + timedelta(seconds=10),
                message="čajnik",
                purpose=OutboundCallPurpose.HOUSEHOLD_SAFETY,
                related_entity_type="reminder",
                related_entity_id=reminder_id,
                idempotency_key=f"call-{attempt}",
            )
            call.status = OutboundCallStatus.NO_ANSWER
        first = FamilyEscalationService(store).after_no_answer(call.id)
        assert first is not None
    async with application_store(durable_settings) as store:
        assert store.appointments[appointment.id].notify_user_ids == [branko.id]
        assert store.appointments[appointment.id].reminder_offsets_minutes == [60]
        assert store.notifications[notification.id].idempotency_key == "notice"
        assert store.outbound_calls[first.id].message == first.message
        assert FamilyEscalationService(store).after_no_answer(call.id).id == first.id


async def test_conversation_is_visible_to_worker(durable_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    state: ConversationState = {
        "call_id": "persistent-conversation",
        "caller_phone": "+385910000001",
        "current_utterance": "podsjeti me za 15 minuta da maknem čajnik s plina",
        "now_iso": datetime.now(UTC).isoformat(),
    }
    state = await conversation_turn(state, durable_settings)
    state["current_utterance"] = "da"
    state = await conversation_turn(state, durable_settings)
    assert state.get("response_text") == "Dogovoreno."
    reminder_id = str(state["tool_result"]["entity_id"])

    class RedisStub:
        async def enqueue_job(self, name: str, call_id: str, **kwargs: Any) -> object:
            assert name == "dispatch_outbound_call"
            async with application_store(durable_settings) as store:
                assert store.outbound_calls[UUID(call_id)].related_entity_id == UUID(reminder_id)
            return object()

    monkeypatch.setattr("app.scheduler.jobs.get_settings", lambda: durable_settings)
    result = await generic_outbound_reminder({"redis": RedisStub()}, reminder_id, "worker-test")
    assert result["queued"] == 1


async def test_upgrade_existing_initial_database(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    engine = create_async_engine(settings.database_url)
    legacy = MemoryStore()
    FamilyDirectory(legacy).seed(settings)
    reminder_id = schedule(legacy, "legacy-key")

    def insert_legacy_rows(connection: Connection) -> None:
        metadata = MetaData()
        metadata.reflect(bind=connection)

        def sqlite_values(values: dict[str, Any]) -> dict[str, Any]:
            # Reflection sees SQLite UUID storage as CHAR(32), without UUID's
            # SQLAlchemy bind processor. Reproduce its stored representation.
            return {key: value.hex if isinstance(value, UUID) else value for key, value in values.items()}

        connection.execute(
            metadata.tables["family_members"].insert(),
            [sqlite_values(member.model_dump()) for member in legacy.family_members.values()],
        )
        connection.execute(
            metadata.tables["reminders"].insert(), sqlite_values(legacy.reminders[reminder_id].model_dump())
        )

    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: migrate(conn, "20260804_0001"))
            old = await connection.run_sync(lambda conn: inspect(conn).get_columns("outbound_calls"))
            assert "message" not in {column["name"] for column in old}
            await connection.run_sync(insert_legacy_rows)
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
            new = await connection.run_sync(lambda conn: inspect(conn).get_columns("outbound_calls"))
            assert {"message", "related_entity_id"} <= {column["name"] for column in new}
    finally:
        await engine.dispose()
    async with application_store(settings) as store:
        assert store.reminders[reminder_id].message == legacy.reminders[reminder_id].message
        assert store.idempotency["legacy-key"] == reminder_id


async def test_json_import_is_atomic_and_preserves_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_path = tmp_path / "original.json"
    source = MemoryStore(source_path)
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'import.db'}")
    FamilyDirectory(source).seed(settings)
    reminder_id = schedule(source)
    before = source_path.read_bytes()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()
    monkeypatch.setattr("scripts.import_development_data.application_store", lambda: application_store(settings))
    await import_data(source_path)
    assert source_path.read_bytes() == before
    async with application_store(settings) as store:
        assert store.reminders[reminder_id].message == source.reminders[reminder_id].message
        assert store.idempotency == source.idempotency
    with pytest.raises(ValueError, match="empty database"):
        await import_data(source_path)
    async with application_store(settings) as store:
        assert len(store.reminders) == 1


async def test_concurrent_medication_confirmation_deducts_once(durable_settings: Settings) -> None:
    async with application_store(durable_settings) as store:
        plan_id, dose_id = medication(store)

    async def report() -> None:
        async with application_store(durable_settings) as store:
            confirm(store, plan_id, dose_id)

    await asyncio.gather(report(), report())
    async with application_store(durable_settings) as store:
        assert store.medication_plans[plan_id].current_inventory == 1
        assert len(store.inventory_events) == 2
