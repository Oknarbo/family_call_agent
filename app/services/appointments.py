"""Doctor appointment lifecycle with explicit user-reported statuses."""

from datetime import datetime
from uuid import UUID

from app.domain.enums import AppointmentStatus
from app.domain.exceptions import DuplicateActionError, NotFoundError
from app.domain.permissions import authorize_family_access
from app.domain.time_parser import validate_future
from app.repositories.protocols import Store
from app.schemas import AppointmentRecord
from app.services.audit import write_audit
from app.utils.datetime import utc_now


class AppointmentService:
    """Manage appointments without inferring attendance from elapsed time."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def create(
        self,
        *,
        requester_user_id: UUID,
        patient_user_id: UUID,
        provider_name: str | None,
        appointment_type: str | None,
        location: str | None,
        scheduled_for: datetime,
        reminder_offsets_minutes: list[int],
        notify_user_ids: list[UUID],
        source_call_id: str,
        idempotency_key: str,
        timezone: str = "Europe/Zagreb",
    ) -> AppointmentRecord:
        authorize_family_access(requester_user_id, patient_user_id)
        if idempotency_key in self.store.idempotency:
            return self.store.appointments[self.store.idempotency[idempotency_key]]
        now = utc_now()
        appointment = AppointmentRecord(
            patient_user_id=patient_user_id,
            created_by_user_id=requester_user_id,
            provider_name=provider_name,
            appointment_type=appointment_type,
            location=location,
            scheduled_for=validate_future(scheduled_for, now=now),
            timezone=timezone,
            status=AppointmentStatus.SCHEDULED,
            source_call_id=source_call_id,
            reminder_offsets_minutes=reminder_offsets_minutes or [1440, 120],
            notify_user_ids=notify_user_ids,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        self.store.appointments[appointment.id] = appointment
        self.store.idempotency[idempotency_key] = appointment.id
        write_audit(
            self.store,
            actor_user_id=requester_user_id,
            action="appointment.created",
            entity_type="doctor_appointment",
            entity_id=appointment.id,
            source_call_id=source_call_id,
            metadata={"patient_user_id": str(patient_user_id)},
        )
        self.store.save()
        return appointment

    def update(
        self,
        *,
        requester_user_id: UUID,
        appointment_id: UUID,
        provider_name: str | None = None,
        appointment_type: str | None = None,
        location: str | None = None,
        scheduled_for: datetime | None = None,
        reminder_offsets_minutes: list[int] | None = None,
        source_call_id: str,
    ) -> AppointmentRecord:
        appointment = self._get(appointment_id)
        authorize_family_access(requester_user_id, appointment.patient_user_id)
        if appointment.status == AppointmentStatus.CANCELLED:
            raise DuplicateActionError
        if provider_name is not None:
            appointment.provider_name = provider_name
        if appointment_type is not None:
            appointment.appointment_type = appointment_type
        if location is not None:
            appointment.location = location
        if scheduled_for is not None:
            appointment.scheduled_for = validate_future(scheduled_for, now=utc_now())
            appointment.status = AppointmentStatus.RESCHEDULED
        if reminder_offsets_minutes is not None:
            appointment.reminder_offsets_minutes = reminder_offsets_minutes
        appointment.updated_at = utc_now()
        write_audit(
            self.store,
            actor_user_id=requester_user_id,
            action="appointment.updated",
            entity_type="doctor_appointment",
            entity_id=appointment.id,
            source_call_id=source_call_id,
        )
        self.store.save()
        return appointment

    def cancel(self, requester_user_id: UUID, appointment_id: UUID, source_call_id: str) -> AppointmentRecord:
        appointment = self._get(appointment_id)
        authorize_family_access(requester_user_id, appointment.patient_user_id)
        appointment.status = AppointmentStatus.CANCELLED
        appointment.updated_at = utc_now()
        write_audit(
            self.store,
            actor_user_id=requester_user_id,
            action="appointment.cancelled",
            entity_type="doctor_appointment",
            entity_id=appointment.id,
            source_call_id=source_call_id,
        )
        self.store.save()
        return appointment

    def upcoming(self, requester_user_id: UUID, patient_user_id: UUID) -> list[AppointmentRecord]:
        authorize_family_access(requester_user_id, patient_user_id)
        valid = {AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED, AppointmentStatus.RESCHEDULED}
        return sorted(
            (
                item
                for item in self.store.appointments.values()
                if item.patient_user_id == patient_user_id and item.status in valid
            ),
            key=lambda item: item.scheduled_for,
        )

    def _get(self, appointment_id: UUID) -> AppointmentRecord:
        try:
            return self.store.appointments[appointment_id]
        except KeyError as exc:
            raise NotFoundError from exc
