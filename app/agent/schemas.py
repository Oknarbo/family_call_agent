"""Pydantic schemas for graph-compatible service tools."""

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import MedicationDoseStatus, OutboundCallPurpose, ReminderType


class ToolSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolResult(ToolSchema):
    ok: bool = True
    entity_id: UUID | None = None
    summary: str
    data: dict[str, object] = Field(default_factory=dict)


class ScheduleReminderInput(ToolSchema):
    requester_user_id: UUID
    target_user_id: UUID
    message: str
    scheduled_for: datetime
    reminder_type: ReminderType
    reminder_subtype: str | None = None
    recurrence_rule: str | None = None
    source_call_id: str
    idempotency_key: str


class CancelReminderInput(ToolSchema):
    requester_user_id: UUID
    reminder_id: UUID
    source_call_id: str


class ListRemindersInput(ToolSchema):
    requester_user_id: UUID
    target_user_id: UUID
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = Field(10, ge=1, le=50)


class ScheduleOutboundCallInput(ToolSchema):
    requester_user_id: UUID
    target_user_id: UUID
    scheduled_for: datetime
    message: str
    purpose: OutboundCallPurpose
    related_entity_type: str
    related_entity_id: UUID
    idempotency_key: str


class CreateMedicationPlanInput(ToolSchema):
    requester_user_id: UUID
    target_user_id: UUID
    medication_display_name: str
    schedule_rule: str
    local_schedule_time: time
    dose_quantity: int = Field(1, gt=0)
    initial_inventory: int | None = Field(None, ge=0)
    low_stock_threshold: int = Field(5, ge=0)
    escalation_contact_user_id: UUID | None = None
    source_call_id: str
    idempotency_key: str


class RecordMedicationResponseInput(ToolSchema):
    user_id: UUID
    medication_plan_id: UUID
    scheduled_dose_event_id: UUID
    reported_status: MedicationDoseStatus
    reported_quantity: int | None = Field(None, gt=0)
    reported_at: datetime
    source_call_id: str
    idempotency_key: str


class UpdateMedicationPlanInput(ToolSchema):
    requester_user_id: UUID
    medication_plan_id: UUID
    schedule_rule: str | None = None
    local_schedule_time: time | None = None
    dose_quantity: int | None = Field(None, gt=0)
    low_stock_threshold: int | None = Field(None, ge=0)
    is_active: bool | None = None
    source_call_id: str


class GetMedicationStatusInput(ToolSchema):
    requester_user_id: UUID
    target_user_id: UUID
    medication_plan_id: UUID | None = None
    medication_name: str | None = None
    date_reference: str | None = None


class MedicationInventoryInput(ToolSchema):
    requester_user_id: UUID
    medication_plan_id: UUID


class AddMedicationInventoryInput(MedicationInventoryInput):
    quantity_to_add: int = Field(gt=0)
    reason: str
    source_call_id: str
    idempotency_key: str


class SetMedicationInventoryInput(MedicationInventoryInput):
    absolute_quantity: int = Field(ge=0)
    reason: str
    source_call_id: str
    idempotency_key: str


class ReverseMedicationConfirmationInput(ToolSchema):
    requester_user_id: UUID
    medication_dose_event_id: UUID
    reason: str
    source_call_id: str
    idempotency_key: str


class CreateAppointmentInput(ToolSchema):
    requester_user_id: UUID
    patient_user_id: UUID
    provider_name: str | None = None
    appointment_type: str | None = None
    location: str | None = None
    scheduled_for: datetime
    reminder_offsets_minutes: list[int] = Field(default_factory=lambda: [1440, 120])
    notify_user_ids: list[UUID] = Field(default_factory=list)
    source_call_id: str
    idempotency_key: str


class UpdateAppointmentInput(ToolSchema):
    requester_user_id: UUID
    appointment_id: UUID
    provider_name: str | None = None
    appointment_type: str | None = None
    location: str | None = None
    scheduled_for: datetime | None = None
    reminder_offsets_minutes: list[int] | None = None
    source_call_id: str


class AppointmentQueryInput(ToolSchema):
    requester_user_id: UUID
    patient_user_id: UUID


class AppointmentListInput(AppointmentQueryInput):
    date_from: datetime | None = None
    date_to: datetime | None = None


class CancelAppointmentInput(ToolSchema):
    requester_user_id: UUID
    appointment_id: UUID
    source_call_id: str


class NotifyFamilyMemberInput(ToolSchema):
    requester_user_id: UUID | None
    target_user_id: UUID
    message: str
    notification_type: str
    related_entity_type: str
    related_entity_id: UUID
    idempotency_key: str
