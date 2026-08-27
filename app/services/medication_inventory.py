"""Auditable, exactly-once tablet inventory updates."""

from uuid import UUID

from app.domain.enums import MedicationInventoryEventType
from app.domain.exceptions import InventoryWouldBeNegativeError, NotFoundError, ValidationError
from app.domain.permissions import authorize_family_access
from app.repositories.protocols import Store
from app.schemas import InventoryEventRecord, MedicationPlanRecord
from app.services.audit import write_audit
from app.utils.datetime import utc_now


class MedicationInventoryService:
    """Apply inventory changes as immutable events."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def _plan(self, plan_id: UUID) -> MedicationPlanRecord:
        try:
            return self.store.medication_plans[plan_id]
        except KeyError as exc:
            raise NotFoundError from exc

    def change(
        self,
        *,
        requester_user_id: UUID,
        medication_plan_id: UUID,
        event_type: MedicationInventoryEventType,
        reason: str,
        source_call_id: str,
        idempotency_key: str,
        quantity_delta: int | None = None,
        absolute_quantity: int | None = None,
        related_dose_event_id: UUID | None = None,
    ) -> InventoryEventRecord:
        plan = self._plan(medication_plan_id)
        authorize_family_access(requester_user_id, plan.user_id)
        if idempotency_key in self.store.idempotency:
            existing = self.store.inventory_events.get(self.store.idempotency[idempotency_key])
            if existing is None:
                raise ValidationError("idempotency key belongs to another action")
            return existing
        previous = plan.current_inventory or 0
        if absolute_quantity is not None:
            new_quantity = absolute_quantity
            delta = new_quantity - previous
        elif quantity_delta is not None:
            delta = quantity_delta
            new_quantity = previous + delta
        else:
            raise ValidationError("missing inventory adjustment")
        if new_quantity < 0:
            raise InventoryWouldBeNegativeError
        now = utc_now()
        event = InventoryEventRecord(
            medication_plan_id=plan.id,
            actor_user_id=requester_user_id,
            event_type=event_type,
            quantity_delta=delta,
            previous_quantity=previous,
            new_quantity=new_quantity,
            reason=reason,
            related_dose_event_id=related_dose_event_id,
            source_call_id=source_call_id,
            idempotency_key=idempotency_key,
            created_at=now,
        )
        plan.current_inventory = new_quantity
        plan.updated_at = now
        self.store.inventory_events[event.id] = event
        self.store.idempotency[idempotency_key] = event.id
        write_audit(
            self.store,
            actor_user_id=requester_user_id,
            action=f"medication_inventory.{event_type.value}",
            entity_type="medication_plan",
            entity_id=plan.id,
            source_call_id=source_call_id,
            metadata={"previous_quantity": previous, "new_quantity": new_quantity},
        )
        self.store.save()
        return event
