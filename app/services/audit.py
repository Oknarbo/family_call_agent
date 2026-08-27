"""Central audit-event creation."""

from typing import Any
from uuid import UUID

from app.repositories.protocols import Store
from app.schemas import AuditRecord
from app.utils.datetime import utc_now


def write_audit(
    store: Store,
    *,
    actor_user_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID,
    source_call_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> AuditRecord:
    """Append a privacy-minimal audit event."""

    event = AuditRecord(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        source_call_id=source_call_id,
        metadata=metadata or {},
        created_at=utc_now(),
    )
    store.audits[event.id] = event
    return event
