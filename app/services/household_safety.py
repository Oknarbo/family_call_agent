"""High-priority household safety reminder policy."""

from datetime import datetime
from uuid import UUID

from app.config import Settings
from app.domain.enums import ReminderType, SafetyReminderOutcome
from app.repositories.protocols import Store
from app.schemas import ReminderRecord
from app.services.reminders import ReminderService


class HouseholdSafetyService:
    """Schedule appliance reminders and derive retry/escalation actions conservatively."""

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.reminders = ReminderService(store)

    def schedule(
        self,
        *,
        requester_user_id: UUID,
        target_user_id: UUID,
        message: str,
        scheduled_for: datetime,
        subtype: str,
        source_call_id: str,
        idempotency_key: str,
    ) -> ReminderRecord:
        return self.reminders.schedule(
            requester_user_id=requester_user_id,
            target_user_id=target_user_id,
            message=message,
            scheduled_for=scheduled_for,
            reminder_type=ReminderType.HOUSEHOLD_SAFETY,
            reminder_subtype=subtype,
            recurrence_rule=None,
            source_call_id=source_call_id,
            idempotency_key=idempotency_key,
            retry_policy={"no_answer_delays_minutes": self.settings.safety_retry_delays_minutes},
            escalation_policy={"notify_after_no_answers": self.settings.safety_escalate_after_no_answers},
        )

    def next_action(self, outcome: SafetyReminderOutcome, attempt_number: int) -> str:
        if outcome == SafetyReminderOutcome.CALL_AGAIN_REQUESTED:
            return "retry"
        if outcome != SafetyReminderOutcome.NO_ANSWER:
            return "complete"
        if attempt_number >= self.settings.safety_escalate_after_no_answers:
            return "escalate"
        if attempt_number <= len(self.settings.safety_retry_delays_minutes):
            return "retry"
        return "complete"
