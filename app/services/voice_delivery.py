"""Resolve scheduled work into outbound Infobip voice calls."""

from datetime import UTC, datetime
from uuid import UUID

import structlog

from app.config import Settings
from app.domain.enums import OutboundCallStatus, ReminderStatus
from app.domain.exceptions import DomainError, NotFoundError, ProviderUnavailableError
from app.repositories.protocols import Store
from app.services.family_directory import FamilyDirectory
from app.telephony.calls import call_mom

logger = structlog.get_logger(__name__)


class VoiceDeliveryService:
    """Load domain records and place outbound voice messages."""

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.directory = FamilyDirectory(store)

    async def deliver(self, kind: str, entity_id: str) -> dict[str, str]:
        target_phone, message, audio_file_url = self._resolve_target(kind, entity_id)
        try:
            placed = await call_mom(
                target_phone,
                message,
                audio_file_url=audio_file_url,
                settings=self.settings,
            )
        except ProviderUnavailableError:
            logger.warning(
                "voice_delivery.skipped",
                kind=kind,
                entity_id=entity_id,
                to_suffix=target_phone[-2:],
            )
            raise
        except DomainError:
            raise
        except Exception as exc:
            logger.exception("voice_delivery.failed", kind=kind, entity_id=entity_id)
            raise ProviderUnavailableError("Slanje glasovne poruke nije uspjelo.") from exc

        self._mark_delivered(kind, entity_id)
        logger.info(
            "voice_delivery.sent",
            kind=kind,
            entity_id=entity_id,
            provider_call_id=placed.provider_call_id,
            status=placed.status,
        )
        return {
            "status": placed.status,
            "kind": kind,
            "entity_id": entity_id,
            "provider_call_id": placed.provider_call_id,
        }

    def _resolve_target(self, kind: str, entity_id: str) -> tuple[str, str, str | None]:
        entity_uuid = UUID(entity_id)
        if kind in {"generic_reminder", "safety_reminder"}:
            return self._from_reminder(entity_uuid)
        if kind == "medication_reminder":
            return self._from_medication_dose(entity_uuid)
        if kind in {
            "appointment_reminder",
            "appointment_followup",
            "medication_retry",
            "safety_retry",
            "safety_escalation",
            "family_notification",
            "low_stock",
        }:
            return self._from_outbound_call(entity_uuid)
        if kind == "medication_dose_creation":
            return self._from_medication_plan(entity_uuid)
        raise NotFoundError

    def _phone_for_user(self, user_id: UUID) -> str:
        return self.directory.by_id(user_id).phone_number_e164

    def _from_reminder(self, reminder_id: UUID) -> tuple[str, str, str | None]:
        try:
            reminder = self.store.reminders[reminder_id]
        except KeyError as exc:
            raise NotFoundError from exc
        phone = self._phone_for_user(reminder.target_user_id)
        message = reminder.message
        audio_url = _optional_audio_url(reminder.retry_policy)
        return phone, message, audio_url

    def _from_outbound_call(self, call_id: UUID) -> tuple[str, str, str | None]:
        try:
            outbound = self.store.outbound_calls[call_id]
        except KeyError as exc:
            raise NotFoundError from exc
        phone = self._phone_for_user(outbound.target_user_id)
        return phone, outbound.message, None

    def _from_medication_dose(self, dose_id: UUID) -> tuple[str, str, str | None]:
        try:
            dose = self.store.medication_doses[dose_id]
            plan = self.store.medication_plans[dose.medication_plan_id]
        except KeyError as exc:
            raise NotFoundError from exc
        phone = self._phone_for_user(dose.user_id)
        message = f"Podsjetnik: vrijeme je za tabletu {plan.display_name}."
        return phone, message, None

    def _from_medication_plan(self, plan_id: UUID) -> tuple[str, str, str | None]:
        try:
            plan = self.store.medication_plans[plan_id]
        except KeyError as exc:
            raise NotFoundError from exc
        phone = self._phone_for_user(plan.user_id)
        message = f"Podsjetnik: vrijeme je za tabletu {plan.display_name}."
        return phone, message, None

    def _mark_delivered(self, kind: str, entity_id: str) -> None:
        entity_uuid = UUID(entity_id)
        now = datetime.now(UTC)
        if kind in {"generic_reminder", "safety_reminder"} and entity_uuid in self.store.reminders:
            reminder = self.store.reminders[entity_uuid]
            reminder.status = ReminderStatus.COMPLETED
            reminder.updated_at = now
        elif entity_uuid in self.store.outbound_calls:
            outbound = self.store.outbound_calls[entity_uuid]
            outbound.status = OutboundCallStatus.COMPLETED
            outbound.updated_at = now
        self.store.save()


def _optional_audio_url(policy: dict[str, object]) -> str | None:
    value = policy.get("audio_file_url")
    return str(value) if isinstance(value, str) and value.strip() else None
