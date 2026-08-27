"""Deterministic development/test store with optional JSON persistence."""

import json
from pathlib import Path
from typing import Any, ClassVar, TypeVar
from uuid import UUID

from pydantic import BaseModel

from app.schemas import (
    AppointmentRecord,
    AuditRecord,
    FamilyMemberRecord,
    InventoryEventRecord,
    MedicationDoseRecord,
    MedicationPlanRecord,
    NotificationRecord,
    OutboundCallRecord,
    ReminderRecord,
)

Record = TypeVar("Record", bound=BaseModel)


class MemoryStore:
    """Simple repository used by the CLI and deterministic suite, never production providers."""

    _collections: ClassVar[dict[str, type[BaseModel]]] = {
        "family_members": FamilyMemberRecord,
        "reminders": ReminderRecord,
        "medication_plans": MedicationPlanRecord,
        "medication_doses": MedicationDoseRecord,
        "inventory_events": InventoryEventRecord,
        "appointments": AppointmentRecord,
        "outbound_calls": OutboundCallRecord,
        "notifications": NotificationRecord,
        "audits": AuditRecord,
    }

    def __init__(self, persistence_path: Path | None = None) -> None:
        self.persistence_path = persistence_path
        self.family_members: dict[UUID, FamilyMemberRecord] = {}
        self.reminders: dict[UUID, ReminderRecord] = {}
        self.medication_plans: dict[UUID, MedicationPlanRecord] = {}
        self.medication_doses: dict[UUID, MedicationDoseRecord] = {}
        self.inventory_events: dict[UUID, InventoryEventRecord] = {}
        self.appointments: dict[UUID, AppointmentRecord] = {}
        self.outbound_calls: dict[UUID, OutboundCallRecord] = {}
        self.notifications: dict[UUID, NotificationRecord] = {}
        self.audits: dict[UUID, AuditRecord] = {}
        self.idempotency: dict[str, UUID] = {}
        if persistence_path and persistence_path.exists():
            self._load()

    def _load(self) -> None:
        if self.persistence_path is None:
            return
        data: dict[str, Any] = json.loads(self.persistence_path.read_text(encoding="utf-8"))
        for name, model in self._collections.items():
            collection: dict[UUID, BaseModel] = {}
            for item in data.get(name, []):
                record = model.model_validate(item)
                record_id = UUID(str(record.model_dump()["id"]))
                collection[record_id] = record
            setattr(self, name, collection)
        self.idempotency = {key: UUID(value) for key, value in data.get("idempotency", {}).items()}

    def save(self) -> None:
        if self.persistence_path is None:
            return
        payload: dict[str, Any] = {
            name: [record.model_dump(mode="json") for record in getattr(self, name).values()]
            for name in self._collections
        }
        payload["idempotency"] = {key: str(value) for key, value in self.idempotency.items()}
        self.persistence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def reset(self) -> None:
        for name in self._collections:
            getattr(self, name).clear()
        self.idempotency.clear()
        self.save()
