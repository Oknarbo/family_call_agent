"""Service-facing persistence contracts."""

from typing import Protocol
from uuid import UUID

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


class Store(Protocol):
    family_members: dict[UUID, FamilyMemberRecord]
    reminders: dict[UUID, ReminderRecord]
    medication_plans: dict[UUID, MedicationPlanRecord]
    medication_doses: dict[UUID, MedicationDoseRecord]
    inventory_events: dict[UUID, InventoryEventRecord]
    appointments: dict[UUID, AppointmentRecord]
    outbound_calls: dict[UUID, OutboundCallRecord]
    notifications: dict[UUID, NotificationRecord]
    audits: dict[UUID, AuditRecord]
    idempotency: dict[str, UUID]

    def save(self) -> None: ...
