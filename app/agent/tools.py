"""Typed LangGraph-compatible tools delegating all decisions to services."""

from decimal import Decimal

from app.agent.schemas import (
    AddMedicationInventoryInput,
    AppointmentListInput,
    AppointmentQueryInput,
    CancelAppointmentInput,
    CancelReminderInput,
    CreateAppointmentInput,
    CreateMedicationPlanInput,
    GetMedicationStatusInput,
    ListRemindersInput,
    MedicationInventoryInput,
    NotifyFamilyMemberInput,
    RecordMedicationResponseInput,
    ReverseMedicationConfirmationInput,
    ScheduleOutboundCallInput,
    ScheduleReminderInput,
    SetMedicationInventoryInput,
    ToolResult,
    UpdateAppointmentInput,
    UpdateMedicationPlanInput,
)
from app.domain.enums import MedicationInventoryEventType
from app.domain.exceptions import NotFoundError
from app.repositories.protocols import Store
from app.services.appointments import AppointmentService
from app.services.audit import write_audit
from app.services.medication_inventory import MedicationInventoryService
from app.services.medication_plans import MedicationPlanService
from app.services.notifications import NotificationService
from app.services.outbound_calls import OutboundCallService
from app.services.reminders import ReminderService
from app.utils.datetime import utc_now


class ToolRegistry:
    """Validated application tool surface shared by graph nodes and future LLM adapters."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.reminders = ReminderService(store)
        self.medications = MedicationPlanService(store)
        self.inventory = MedicationInventoryService(store)
        self.appointments = AppointmentService(store)
        self.outbound = OutboundCallService(store)
        self.notifications = NotificationService(store)

    def schedule_reminder(self, raw: ScheduleReminderInput) -> ToolResult:
        record = self.reminders.schedule(**raw.model_dump())
        return ToolResult(
            entity_id=record.id,
            summary="Podsjetnik je dogovoren.",
            data={"scheduled_for": record.scheduled_for.isoformat()},
        )

    def cancel_reminder(self, raw: CancelReminderInput) -> ToolResult:
        record = self.reminders.cancel(**raw.model_dump())
        return ToolResult(entity_id=record.id, summary="Podsjetnik je otkazan.")

    def list_upcoming_reminders(self, raw: ListRemindersInput) -> ToolResult:
        records = self.reminders.upcoming(**raw.model_dump())
        return ToolResult(
            summary=f"Pronašao sam {len(records)} podsjetnika.",
            data={"items": [record.model_dump(mode="json") for record in records]},
        )

    def schedule_outbound_call(self, raw: ScheduleOutboundCallInput) -> ToolResult:
        record = self.outbound.schedule(**raw.model_dump())
        return ToolResult(entity_id=record.id, summary="Poziv je dogovoren.")

    def create_medication_plan(self, raw: CreateMedicationPlanInput) -> ToolResult:
        record = self.medications.create_plan(**raw.model_dump())
        return ToolResult(
            entity_id=record.id,
            summary="Plan tableta je dogovoren.",
            data={"current_inventory": record.current_inventory},
        )

    def update_medication_plan(self, raw: UpdateMedicationPlanInput) -> ToolResult:
        try:
            plan = self.store.medication_plans[raw.medication_plan_id]
        except KeyError as exc:
            raise NotFoundError from exc
        if raw.schedule_rule is not None:
            plan.schedule_rule = raw.schedule_rule
        if raw.local_schedule_time is not None:
            plan.local_schedule_time = raw.local_schedule_time
        if raw.dose_quantity is not None:
            plan.dose_quantity = Decimal(raw.dose_quantity)
        if raw.low_stock_threshold is not None:
            plan.low_stock_threshold = raw.low_stock_threshold
        if raw.is_active is not None:
            plan.is_active = raw.is_active
        plan.updated_at = utc_now()
        write_audit(
            self.store,
            actor_user_id=raw.requester_user_id,
            action="medication_plan.updated",
            entity_type="medication_plan",
            entity_id=plan.id,
            source_call_id=raw.source_call_id,
        )
        self.store.save()
        return ToolResult(entity_id=plan.id, summary="Plan tableta je promijenjen.")

    def record_medication_response(self, raw: RecordMedicationResponseInput) -> ToolResult:
        dose = self.medications.record_response(**raw.model_dump())
        plan = self.store.medication_plans[dose.medication_plan_id]
        return ToolResult(
            entity_id=dose.id,
            summary="Zabilježio sam ono što je korisnik rekao.",
            data={"reported_status": dose.status.value, "current_inventory": plan.current_inventory},
        )

    def get_medication_status(self, raw: GetMedicationStatusInput) -> ToolResult:
        plans = self.medications.plans_for(raw.requester_user_id, raw.target_user_id)
        if raw.medication_plan_id is not None:
            plans = [plan for plan in plans if plan.id == raw.medication_plan_id]
        if raw.medication_name is not None:
            plans = [plan for plan in plans if raw.medication_name.casefold() in plan.display_name.casefold()]
        if not plans:
            raise NotFoundError
        plan = plans[0]
        doses = [dose for dose in self.store.medication_doses.values() if dose.medication_plan_id == plan.id]
        latest = max(doses, key=lambda dose: dose.scheduled_for) if doses else None
        return ToolResult(
            entity_id=plan.id,
            summary="Pronašao sam podatke o tableti.",
            data={
                "current_inventory": plan.current_inventory,
                "latest_reported_status": latest.status.value if latest else None,
            },
        )

    def get_medication_inventory(self, raw: MedicationInventoryInput) -> ToolResult:
        plan = self.store.medication_plans.get(raw.medication_plan_id)
        if plan is None:
            raise NotFoundError
        self.medications.plans_for(raw.requester_user_id, plan.user_id)
        return ToolResult(
            entity_id=plan.id,
            summary=(
                "Stanje tableta nije uneseno."
                if plan.current_inventory is None
                else f"Prema evidenciji ostalo je {plan.current_inventory} tableta."
            ),
            data={"current_inventory": plan.current_inventory},
        )

    def add_medication_inventory(self, raw: AddMedicationInventoryInput) -> ToolResult:
        event = self.inventory.change(
            requester_user_id=raw.requester_user_id,
            medication_plan_id=raw.medication_plan_id,
            event_type=MedicationInventoryEventType.BOX_ADDED,
            quantity_delta=raw.quantity_to_add,
            reason=raw.reason,
            source_call_id=raw.source_call_id,
            idempotency_key=raw.idempotency_key,
        )
        return ToolResult(
            entity_id=event.id,
            summary=f"Prema evidenciji sada ima {event.new_quantity} tableta.",
            data={"current_inventory": event.new_quantity},
        )

    def set_medication_inventory(self, raw: SetMedicationInventoryInput) -> ToolResult:
        event = self.inventory.change(
            requester_user_id=raw.requester_user_id,
            medication_plan_id=raw.medication_plan_id,
            event_type=MedicationInventoryEventType.MANUAL_CORRECTION,
            absolute_quantity=raw.absolute_quantity,
            reason=raw.reason,
            source_call_id=raw.source_call_id,
            idempotency_key=raw.idempotency_key,
        )
        return ToolResult(
            entity_id=event.id,
            summary=f"Stanje je ispravljeno na {event.new_quantity} tableta.",
        )

    def reverse_medication_confirmation(self, raw: ReverseMedicationConfirmationInput) -> ToolResult:
        dose = self.medications.reverse_confirmation(**raw.model_dump())
        return ToolResult(entity_id=dose.id, summary="Jučerašnja potvrda je ispravljena.")

    def create_doctor_appointment(self, raw: CreateAppointmentInput) -> ToolResult:
        appointment = self.appointments.create(**raw.model_dump())
        return ToolResult(entity_id=appointment.id, summary="Pregled je dogovoren.")

    def update_doctor_appointment(self, raw: UpdateAppointmentInput) -> ToolResult:
        appointment = self.appointments.update(**raw.model_dump())
        return ToolResult(entity_id=appointment.id, summary="Pregled je promijenjen.")

    def cancel_doctor_appointment(self, raw: CancelAppointmentInput) -> ToolResult:
        appointment = self.appointments.cancel(**raw.model_dump())
        return ToolResult(entity_id=appointment.id, summary="Pregled je otkazan.")

    def get_next_doctor_appointment(self, raw: AppointmentQueryInput) -> ToolResult:
        items = self.appointments.upcoming(**raw.model_dump())
        if not items:
            return ToolResult(summary="Nema nadolazećih pregleda.")
        appointment = items[0]
        return ToolResult(
            entity_id=appointment.id,
            summary="Pronašao sam sljedeći pregled.",
            data=appointment.model_dump(mode="json"),
        )

    def list_doctor_appointments(self, raw: AppointmentListInput) -> ToolResult:
        items = self.appointments.upcoming(raw.requester_user_id, raw.patient_user_id)
        if raw.date_from:
            items = [item for item in items if item.scheduled_for >= raw.date_from]
        if raw.date_to:
            items = [item for item in items if item.scheduled_for <= raw.date_to]
        return ToolResult(
            summary=f"Pronašao sam {len(items)} pregleda.",
            data={"items": [item.model_dump(mode="json") for item in items]},
        )

    def notify_family_member(self, raw: NotifyFamilyMemberInput) -> ToolResult:
        record = self.notifications.create(**raw.model_dump())
        return ToolResult(entity_id=record.id, summary="Poruka je pripremljena.")
