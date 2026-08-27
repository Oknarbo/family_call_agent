"""Idempotent outbound-call scheduling independent of telephony provider."""

from datetime import datetime
from uuid import UUID

from app.domain.enums import OutboundCallPurpose
from app.domain.permissions import authorize_family_access
from app.domain.time_parser import validate_future
from app.repositories.protocols import Store
from app.schemas import OutboundCallRecord
from app.services.audit import write_audit
from app.utils.datetime import utc_now


class OutboundCallService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def schedule(
        self,
        *,
        requester_user_id: UUID,
        target_user_id: UUID,
        scheduled_for: datetime,
        message: str,
        purpose: OutboundCallPurpose,
        related_entity_type: str,
        related_entity_id: UUID,
        idempotency_key: str,
    ) -> OutboundCallRecord:
        authorize_family_access(requester_user_id, target_user_id)
        if idempotency_key in self.store.idempotency:
            return self.store.outbound_calls[self.store.idempotency[idempotency_key]]
        now = utc_now()
        call = OutboundCallRecord(
            target_user_id=target_user_id,
            scheduled_for=validate_future(scheduled_for, now=now),
            purpose=purpose,
            message=message,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        self.store.outbound_calls[call.id] = call
        self.store.idempotency[idempotency_key] = call.id
        write_audit(
            self.store,
            actor_user_id=requester_user_id,
            action="outbound_call.scheduled",
            entity_type="outbound_call",
            entity_id=call.id,
            source_call_id=None,
        )
        self.store.save()
        return call
