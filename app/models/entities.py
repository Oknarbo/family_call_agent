"""Persisted domain entities for PostgreSQL and development SQLite."""

import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import (
    AppointmentReminderOutcome,
    AppointmentStatus,
    CallDirection,
    CallStatus,
    DeliveryStatus,
    FamilyRole,
    MedicationDoseStatus,
    MedicationInventoryEventType,
    OutboundCallPurpose,
    OutboundCallStatus,
    ReminderStatus,
    ReminderType,
)
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def enum_column(enum_type: type[Any]) -> Enum:
    return Enum(enum_type, native_enum=False, values_callable=lambda items: [item.value for item in items])


class FamilyMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "family_members"
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    phone_number_e164: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    role: Mapped[FamilyRole] = mapped_column(enum_column(FamilyRole), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Zagreb", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notification_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    escalation_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    preferred_assistant_wording: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class CallSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "call_sessions"
    provider_call_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    direction: Mapped[CallDirection] = mapped_column(enum_column(CallDirection), nullable=False)
    caller_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("family_members.id"))
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("family_members.id"))
    caller_phone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[CallStatus] = mapped_column(enum_column(CallStatus), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transcript_summary: Mapped[str | None] = mapped_column(Text)


class Reminder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reminders"
    requester_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    target_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    reminder_type: Mapped[ReminderType] = mapped_column(enum_column(ReminderType), nullable=False)
    reminder_subtype: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[ReminderStatus] = mapped_column(enum_column(ReminderStatus), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_call_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    retry_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    escalation_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class MedicationPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "medication_plans"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    instructions_label: Mapped[str | None] = mapped_column(String(255))
    dose_quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    schedule_rule: Mapped[str] = mapped_column(String(255), nullable=False)
    local_schedule_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    current_inventory: Mapped[int | None] = mapped_column(Integer)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    escalation_contact_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("family_members.id"))


class MedicationDoseEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "medication_dose_events"
    medication_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medication_plans.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[MedicationDoseStatus] = mapped_column(enum_column(MedicationDoseStatus), nullable=False)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("family_members.id"))
    reported_quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    source_call_id: Mapped[str | None] = mapped_column(String(128))
    inventory_adjustment_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)


class MedicationInventoryEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "medication_inventory_events"
    medication_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medication_plans.id"), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    event_type: Mapped[MedicationInventoryEventType] = mapped_column(
        enum_column(MedicationInventoryEventType), nullable=False
    )
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    new_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    related_dose_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("medication_dose_events.id"))
    source_call_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DoctorAppointment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "doctor_appointments"
    patient_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(160))
    appointment_type: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(255))
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AppointmentStatus] = mapped_column(enum_column(AppointmentStatus), nullable=False)
    source_call_id: Mapped[str | None] = mapped_column(String(128))


class AppointmentReminder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "appointment_reminders"
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("doctor_appointments.id"), nullable=False)
    target_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reminder_offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReminderStatus] = mapped_column(enum_column(ReminderStatus), nullable=False)
    outcome: Mapped[AppointmentReminderOutcome | None] = mapped_column(enum_column(AppointmentReminderOutcome))
    outbound_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outbound_calls.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)


class OutboundCall(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outbound_calls"
    target_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    reminder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reminders.id"))
    medication_dose_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("medication_dose_events.id"))
    appointment_reminder_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("appointment_reminders.id"))
    provider_call_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    purpose: Mapped[OutboundCallPurpose] = mapped_column(enum_column(OutboundCallPurpose), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[OutboundCallStatus] = mapped_column(enum_column(OutboundCallStatus), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"
    target_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("family_members.id"), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    related_entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    delivery_channel: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(enum_column(DeliveryStatus), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("family_members.id"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    source_call_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
