"""Medication plans and user-reported dose outcomes."""

from datetime import datetime, time
from decimal import Decimal
from uuid import UUID

from app.domain.enums import (
    MedicationDoseStatus,
    MedicationInventoryEventType,
)
from app.domain.exceptions import DuplicateActionError, NotFoundError, ValidationError
from app.domain.medication_rules import should_decrement_inventory
from app.domain.permissions import authorize_family_access
from app.repositories.protocols import Store
from app.schemas import MedicationDoseRecord, MedicationPlanRecord
from app.services.audit import write_audit
from app.services.medication_inventory import MedicationInventoryService
from app.utils.datetime import utc_now


class MedicationPlanService:
    """Keep medication records explicitly self-reported and inventory-safe."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.inventory = MedicationInventoryService(store)

    def create_plan(
        self,
        *,
        requester_user_id: UUID,
        target_user_id: UUID,
        medication_display_name: str,
        schedule_rule: str,
        local_schedule_time: time,
        dose_quantity: int,
        initial_inventory: int | None,
        low_stock_threshold: int,
        escalation_contact_user_id: UUID | None,
        source_call_id: str,
        idempotency_key: str,
        timezone: str = "Europe/Zagreb",
    ) -> MedicationPlanRecord:
        authorize_family_access(requester_user_id, target_user_id)
        if dose_quantity <= 0 or low_stock_threshold < 0:
            raise ValidationError
        if initial_inventory is not None and initial_inventory < 0:
            raise ValidationError
        if idempotency_key in self.store.idempotency:
            return self.store.medication_plans[self.store.idempotency[idempotency_key]]
        now = utc_now()
        plan = MedicationPlanRecord(
            user_id=target_user_id,
            display_name=medication_display_name.strip(),
            instructions_label=medication_display_name.strip(),
            dose_quantity=Decimal(dose_quantity),
            schedule_rule=schedule_rule,
            local_schedule_time=local_schedule_time,
            timezone=timezone,
            current_inventory=0 if initial_inventory is not None else None,
            low_stock_threshold=low_stock_threshold,
            escalation_contact_user_id=escalation_contact_user_id,
            created_at=now,
            updated_at=now,
        )
        self.store.medication_plans[plan.id] = plan
        self.store.idempotency[idempotency_key] = plan.id
        write_audit(
            self.store,
            actor_user_id=requester_user_id,
            action="medication_plan.created",
            entity_type="medication_plan",
            entity_id=plan.id,
            source_call_id=source_call_id,
            metadata={"target_user_id": str(target_user_id)},
        )
        if initial_inventory is not None:
            self.inventory.change(
                requester_user_id=requester_user_id,
                medication_plan_id=plan.id,
                event_type=MedicationInventoryEventType.INITIAL_STOCK,
                absolute_quantity=initial_inventory,
                reason="Početno stanje",
                source_call_id=source_call_id,
                idempotency_key=f"{idempotency_key}:initial-stock",
            )
        self.store.save()
        return plan

    def create_dose(
        self, medication_plan_id: UUID, scheduled_for: datetime, idempotency_key: str
    ) -> MedicationDoseRecord:
        if idempotency_key in self.store.idempotency:
            return self.store.medication_doses[self.store.idempotency[idempotency_key]]
        try:
            plan = self.store.medication_plans[medication_plan_id]
        except KeyError as exc:
            raise NotFoundError from exc
        now = utc_now()
        dose = MedicationDoseRecord(
            medication_plan_id=plan.id,
            user_id=plan.user_id,
            scheduled_for=scheduled_for,
            created_at=now,
            updated_at=now,
        )
        self.store.medication_doses[dose.id] = dose
        self.store.idempotency[idempotency_key] = dose.id
        self.store.save()
        return dose

    def record_response(
        self,
        *,
        user_id: UUID,
        medication_plan_id: UUID,
        scheduled_dose_event_id: UUID,
        reported_status: MedicationDoseStatus,
        reported_quantity: int | None,
        reported_at: datetime,
        source_call_id: str,
        idempotency_key: str,
    ) -> MedicationDoseRecord:
        try:
            plan = self.store.medication_plans[medication_plan_id]
            dose = self.store.medication_doses[scheduled_dose_event_id]
        except KeyError as exc:
            raise NotFoundError from exc
        if dose.medication_plan_id != plan.id or dose.user_id != user_id:
            raise ValidationError
        if idempotency_key in self.store.idempotency:
            return dose
        if dose.status == MedicationDoseStatus.USER_REPORTED_TAKEN:
            raise DuplicateActionError
        dose.status = reported_status
        dose.reported_at = reported_at
        dose.reported_by_user_id = user_id
        dose.reported_quantity = Decimal(reported_quantity or plan.dose_quantity)
        dose.source_call_id = source_call_id
        dose.updated_at = utc_now()
        self.store.idempotency[idempotency_key] = dose.id
        if should_decrement_inventory(reported_status) and plan.current_inventory is not None:
            event = self.inventory.change(
                requester_user_id=user_id,
                medication_plan_id=plan.id,
                event_type=MedicationInventoryEventType.DOSE_CONFIRMED,
                quantity_delta=-int(dose.reported_quantity),
                reason="Korisnik je potvrdio uzimanje doze",
                related_dose_event_id=dose.id,
                source_call_id=source_call_id,
                idempotency_key=f"dose:{dose.id}:inventory",
            )
            dose.inventory_adjustment_id = event.id
        write_audit(
            self.store,
            actor_user_id=user_id,
            action="medication_dose.user_reported",
            entity_type="medication_dose",
            entity_id=dose.id,
            source_call_id=source_call_id,
            metadata={"reported_status": reported_status.value},
        )
        self.store.save()
        return dose

    def reverse_confirmation(
        self,
        *,
        requester_user_id: UUID,
        medication_dose_event_id: UUID,
        reason: str,
        source_call_id: str,
        idempotency_key: str,
    ) -> MedicationDoseRecord:
        try:
            dose = self.store.medication_doses[medication_dose_event_id]
        except KeyError as exc:
            raise NotFoundError from exc
        if dose.status != MedicationDoseStatus.USER_REPORTED_TAKEN or dose.inventory_adjustment_id is None:
            raise ValidationError("dose has no deduction to reverse")
        plan = self.store.medication_plans[dose.medication_plan_id]
        adjustment = self.store.inventory_events[dose.inventory_adjustment_id]
        self.inventory.change(
            requester_user_id=requester_user_id,
            medication_plan_id=plan.id,
            event_type=MedicationInventoryEventType.REVERSAL,
            quantity_delta=-adjustment.quantity_delta,
            reason=reason,
            related_dose_event_id=dose.id,
            source_call_id=source_call_id,
            idempotency_key=idempotency_key,
        )
        dose.status = MedicationDoseStatus.USER_REPORTED_NOT_TAKEN
        dose.notes = reason
        self.store.save()
        return dose

    def plans_for(self, requester_user_id: UUID, target_user_id: UUID) -> list[MedicationPlanRecord]:
        authorize_family_access(requester_user_id, target_user_id)
        return [plan for plan in self.store.medication_plans.values() if plan.user_id == target_user_id]

    def is_low_stock(self, medication_plan_id: UUID) -> bool:
        """Report the configured threshold without using alarmist inference."""

        try:
            plan = self.store.medication_plans[medication_plan_id]
        except KeyError as exc:
            raise NotFoundError from exc
        return plan.current_inventory is not None and plan.current_inventory <= plan.low_stock_threshold
