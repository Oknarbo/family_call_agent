"""Transport-independent validated records used by services and tools."""

from datetime import datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    AppointmentStatus,
    DeliveryStatus,
    FamilyRole,
    MedicationDoseStatus,
    MedicationInventoryEventType,
    OutboundCallPurpose,
    OutboundCallStatus,
    ReminderStatus,
    ReminderType,
)


class DomainRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FamilyMemberRecord(DomainRecord):
    id: UUID = Field(default_factory=uuid4)
    display_name: str
    phone_number_e164: str
    role: FamilyRole
    timezone: str = "Europe/Zagreb"
    is_active: bool = True
    notification_preferences: dict[str, Any] = Field(default_factory=dict)
    escalation_preferences: dict[str, Any] = Field(default_factory=dict)
    preferred_assistant_wording: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ReminderRecord(DomainRecord):
    id: UUID = Field(default_factory=uuid4)
    requester_user_id: UUID
    target_user_id: UUID
    reminder_type: ReminderType
    reminder_subtype: str | None = None
    message: str
    scheduled_for: datetime
    timezone: str = "Europe/Zagreb"
    recurrence_rule: str | None = None
    status: ReminderStatus = ReminderStatus.SCHEDULED
    priority: int = 0
    source_call_id: str | None = None
    idempotency_key: str
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    escalation_policy: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class MedicationPlanRecord(DomainRecord):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    display_name: str
    instructions_label: str | None = None
    dose_quantity: Decimal = Decimal("1")
    schedule_rule: str
    local_schedule_time: time
    timezone: str = "Europe/Zagreb"
    current_inventory: int | None = None
    low_stock_threshold: int = 5
    is_active: bool = True
    escalation_contact_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class MedicationDoseRecord(DomainRecord):
    id: UUID = Field(default_factory=uuid4)
    medication_plan_id: UUID
    user_id: UUID
    scheduled_for: datetime
    status: MedicationDoseStatus = MedicationDoseStatus.SCHEDULED
    reported_at: datetime | None = None
    reported_by_user_id: UUID | None = None
    reported_quantity: Decimal | None = None
    source_call_id: str | None = None
    inventory_adjustment_id: UUID | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class InventoryEventRecord(DomainRecord):
    id: UUID = Field(default_factory=uuid4)
    medication_plan_id: UUID
    actor_user_id: UUID
    event_type: MedicationInventoryEventType
    quantity_delta: int
    previous_quantity: int
    new_quantity: int
    reason: str
    related_dose_event_id: UUID | None = None
    source_call_id: str | None = None
    idempotency_key: str
    created_at: datetime


class AppointmentRecord(DomainRecord):
    id: UUID = Field(default_factory=uuid4)
    patient_user_id: UUID
    created_by_user_id: UUID
    provider_name: str | None = None
    appointment_type: str | None = None
    location: str | None = None
    scheduled_for: datetime
    timezone: str = "Europe/Zagreb"
    notes: str | None = None
    status: AppointmentStatus = AppointmentStatus.SCHEDULED
    source_call_id: str | None = None
    reminder_offsets_minutes: list[int] = Field(default_factory=lambda: [1440, 120])
    notify_user_ids: list[UUID] = Field(default_factory=list)
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class OutboundCallRecord(DomainRecord):
    id: UUID = Field(default_factory=uuid4)
    target_user_id: UUID
    scheduled_for: datetime
    purpose: OutboundCallPurpose
    message: str
    related_entity_type: str
    related_entity_id: UUID
    status: OutboundCallStatus = OutboundCallStatus.SCHEDULED
    attempt_number: int = 1
    provider_call_id: str | None = None
    started_at: datetime | None = None
    answered_at: datetime | None = None
    ended_at: datetime | None = None
    occurrence_for: datetime | None = None
    source_version: str = ""
    priority: int = 0
    error_code: str | None = None
    user_outcome: str | None = None
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class NotificationRecord(DomainRecord):
    id: UUID = Field(default_factory=uuid4)
    target_user_id: UUID
    notification_type: str
    message: str
    related_entity_type: str
    related_entity_id: UUID
    delivery_channel: str = "call"
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING
    idempotency_key: str
    created_at: datetime
    delivered_at: datetime | None = None


class AuditRecord(DomainRecord):
    id: UUID = Field(default_factory=uuid4)
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_call_id: str | None = None
    created_at: datetime
