"""Generic and household reminder lifecycle."""

from datetime import datetime
from uuid import UUID

from app.domain.enums import ReminderStatus, ReminderType
from app.domain.exceptions import DuplicateActionError, NotFoundError
from app.domain.permissions import authorize_family_access
from app.domain.time_parser import validate_future
from app.repositories.protocols import Store
from app.schemas import ReminderRecord
from app.services.audit import write_audit
from app.utils.datetime import utc_now


class ReminderService:
    """Schedule and query idempotent family reminders."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def schedule(
        self,
        *,
        requester_user_id: UUID,
        target_user_id: UUID,
        message: str,
        scheduled_for: datetime,
        reminder_type: ReminderType,
        reminder_subtype: str | None,
        recurrence_rule: str | None,
        source_call_id: str,
        idempotency_key: str,
        timezone: str = "Europe/Zagreb",
        retry_policy: dict[str, object] | None = None,
        escalation_policy: dict[str, object] | None = None,
    ) -> ReminderRecord:
        authorize_family_access(requester_user_id, target_user_id)
        if idempotency_key in self.store.idempotency:
            existing_id = self.store.idempotency[idempotency_key]
            return self.store.reminders[existing_id]
        now = utc_now()
        reminder = ReminderRecord(
            requester_user_id=requester_user_id,
            target_user_id=target_user_id,
            message=message.strip(),
            scheduled_for=validate_future(scheduled_for, now=now),
            reminder_type=reminder_type,
            reminder_subtype=reminder_subtype,
            recurrence_rule=recurrence_rule,
            status=ReminderStatus.SCHEDULED,
            timezone=timezone,
            priority=10 if reminder_type == ReminderType.HOUSEHOLD_SAFETY else 0,
            source_call_id=source_call_id,
            idempotency_key=idempotency_key,
            retry_policy=retry_policy or {},
            escalation_policy=escalation_policy or {},
            created_at=now,
            updated_at=now,
        )
        self.store.reminders[reminder.id] = reminder
        self.store.idempotency[idempotency_key] = reminder.id
        write_audit(
            self.store,
            actor_user_id=requester_user_id,
            action="reminder.scheduled",
            entity_type="reminder",
            entity_id=reminder.id,
            source_call_id=source_call_id,
            metadata={"target_user_id": str(target_user_id), "type": reminder_type.value},
        )
        self.store.save()
        return reminder

    def cancel(self, requester_user_id: UUID, reminder_id: UUID, source_call_id: str) -> ReminderRecord:
        try:
            reminder = self.store.reminders[reminder_id]
        except KeyError as exc:
            raise NotFoundError from exc
        authorize_family_access(requester_user_id, reminder.target_user_id)
        if reminder.status == ReminderStatus.COMPLETED:
            raise DuplicateActionError("completed reminder cannot be cancelled")
        reminder.status = ReminderStatus.CANCELLED
        reminder.updated_at = utc_now()
        write_audit(
            self.store,
            actor_user_id=requester_user_id,
            action="reminder.cancelled",
            entity_type="reminder",
            entity_id=reminder.id,
            source_call_id=source_call_id,
        )
        self.store.save()
        return reminder

    def upcoming(
        self,
        requester_user_id: UUID,
        target_user_id: UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 10,
    ) -> list[ReminderRecord]:
        authorize_family_access(requester_user_id, target_user_id)
        items = [
            item
            for item in self.store.reminders.values()
            if item.target_user_id == target_user_id
            and item.status == ReminderStatus.SCHEDULED
            and (date_from is None or item.scheduled_for >= date_from)
            and (date_to is None or item.scheduled_for <= date_to)
        ]
        return sorted(items, key=lambda item: item.scheduled_for)[:limit]
