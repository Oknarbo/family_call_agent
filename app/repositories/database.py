"""Transactional SQL store for the single-family deployment.

Services work on a transaction-local snapshot. Their save() calls never commit
partial actions: the outer unit of work flushes all records and idempotency keys
together. A database lock serializes family mutations across API/worker processes.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Base
from app.models.entities import (
    AuditEvent,
    DoctorAppointment,
    FamilyMember,
    IdempotencyEntry,
    MedicationDoseEvent,
    MedicationInventoryEvent,
    MedicationPlan,
    Notification,
    OutboundCall,
    Reminder,
)
from app.repositories.memory import MemoryStore

# Foreign-key order: parents are flushed before dependent inserts.
TABLES: dict[str, type[Base]] = {
    "family_members": FamilyMember,
    "medication_plans": MedicationPlan,
    "medication_doses": MedicationDoseEvent,
    "inventory_events": MedicationInventoryEvent,
    "reminders": Reminder,
    "appointments": DoctorAppointment,
    "outbound_calls": OutboundCall,
    "notifications": Notification,
    "audits": AuditEvent,
}


class DatabaseStore(MemoryStore):
    """Snapshot valid for one transaction only; never cache this object."""

    def __init__(self) -> None:
        super().__init__()
        self.rollback_only = False
        self._rows: dict[str, dict[UUID, Base]] = {}
        self._original: dict[str, dict[UUID, dict[str, Any]]] = {}
        self._original_keys: dict[str, UUID] = {}

    def save(self) -> None:
        """Commit is deliberately deferred to database_store()."""

    def abort(self) -> None:
        self.rollback_only = True

    async def load(self, session: AsyncSession) -> None:
        for name, table in TABLES.items():
            schema = self._collections[name]
            rows = (await session.scalars(select(table))).all()
            self._rows[name] = {}
            collection = getattr(self, name)
            for row in rows:
                values = {
                    field: deepcopy(getattr(row, "metadata_json" if field == "metadata" else field))
                    for field in schema.model_fields
                }
                # SQLite drops timezone information; persisted timestamps are UTC.
                for field, value in values.items():
                    if isinstance(value, datetime) and value.tzinfo is None:
                        values[field] = value.replace(tzinfo=UTC)
                # Legacy SQL rows predate conversational idempotency/relationships.
                if "idempotency_key" in values and values["idempotency_key"] is None:
                    values["idempotency_key"] = f"legacy:{name}:{values['id']}"
                if name == "outbound_calls" and values["related_entity_id"] is None:
                    values["related_entity_id"] = values["id"]
                record = schema.model_validate(values)
                collection[values["id"]] = record
                self._rows[name][values["id"]] = row
            self._original[name] = {key: value.model_dump() for key, value in collection.items()}
        entries = (await session.scalars(select(IdempotencyEntry))).all()
        self.idempotency = {entry.key: entry.entity_id for entry in entries}
        self._original_keys = dict(self.idempotency)

    async def flush(self, session: AsyncSession) -> None:
        for name, table in TABLES.items():
            collection = getattr(self, name)
            if self._original[name].keys() - collection.keys():
                raise ValueError("SQL records must be cancelled/deactivated, not deleted from a snapshot")
            for record_id, record in collection.items():
                values = record.model_dump()
                if values == self._original[name].get(record_id):
                    continue
                row = self._rows[name].get(record_id)
                if row is None:
                    row = table()
                    session.add(row)
                for field, value in values.items():
                    if field == "notify_user_ids":
                        value = [str(item) for item in value]
                    setattr(row, "metadata_json" if field == "metadata" else field, deepcopy(value))
            await session.flush()
        if self._original_keys.keys() - self.idempotency.keys():
            raise ValueError("Idempotency history cannot be removed")
        for key, entity_id in self.idempotency.items():
            if key in self._original_keys:
                if self._original_keys[key] != entity_id:
                    raise ValueError("Idempotency key cannot be reassigned")
            else:
                session.add(IdempotencyEntry(key=key, entity_id=entity_id))
        await session.flush()


@asynccontextmanager
async def database_store(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[DatabaseStore]:
    """Read fresh state under a cross-process lock and commit once on success."""
    async with factory() as session, session.begin():
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(982734601)"))
        elif dialect == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))
        else:
            raise ValueError(f"Unsupported store dialect: {dialect}")
        store = DatabaseStore()
        await store.load(session)
        yield store
        if not store.rollback_only:
            await store.flush(session)
