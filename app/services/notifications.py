"""Family notification records; provider delivery happens asynchronously."""

from uuid import UUID

from app.domain.permissions import authorize_family_access
from app.repositories.protocols import Store
from app.schemas import NotificationRecord
from app.services.audit import write_audit
from app.utils.datetime import utc_now


class NotificationService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def create(
        self,
        *,
        requester_user_id: UUID | None,
        target_user_id: UUID,
        message: str,
        notification_type: str,
        related_entity_type: str,
        related_entity_id: UUID,
        idempotency_key: str,
    ) -> NotificationRecord:
        authorize_family_access(requester_user_id, target_user_id)
        if idempotency_key in self.store.idempotency:
            return self.store.notifications[self.store.idempotency[idempotency_key]]
        record = NotificationRecord(
            target_user_id=target_user_id,
            notification_type=notification_type,
            message=message,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            idempotency_key=idempotency_key,
            created_at=utc_now(),
        )
        self.store.notifications[record.id] = record
        self.store.idempotency[idempotency_key] = record.id
        write_audit(
            self.store,
            actor_user_id=requester_user_id,
            action="notification.created",
            entity_type="notification",
            entity_id=record.id,
            source_call_id=None,
        )
        self.store.save()
        return record
