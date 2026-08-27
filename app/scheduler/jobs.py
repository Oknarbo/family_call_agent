"""Retry-safe ARQ job entry points."""

from typing import Any

import structlog

from app.config import get_settings
from app.dependencies import development_store
from app.domain.exceptions import DomainError, ProviderUnavailableError
from app.scheduler.idempotency import redis_lock
from app.services.voice_delivery import VoiceDeliveryService

logger = structlog.get_logger(__name__)


async def _run_once(ctx: dict[str, Any], kind: str, entity_id: str, idempotency_key: str) -> dict[str, str]:
    redis = ctx["redis"]
    async with redis_lock(redis, idempotency_key) as acquired:
        if not acquired:
            return {"status": "duplicate_skipped", "kind": kind, "entity_id": entity_id}
        settings = get_settings()
        delivery = VoiceDeliveryService(development_store(), settings)
        try:
            return await delivery.deliver(kind, entity_id)
        except ProviderUnavailableError as exc:
            logger.warning("scheduler.job.provider_unavailable", kind=kind, entity_id=entity_id, error=exc.code)
            return {"status": "provider_unavailable", "kind": kind, "entity_id": entity_id}
        except DomainError as exc:
            logger.warning("scheduler.job.domain_error", kind=kind, entity_id=entity_id, error=exc.code)
            return {"status": exc.code, "kind": kind, "entity_id": entity_id}


async def generic_outbound_reminder(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "generic_reminder", entity_id, idempotency_key)


async def create_recurring_medication_dose(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "medication_dose_creation", entity_id, idempotency_key)


async def medication_reminder_call(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "medication_reminder", entity_id, idempotency_key)


async def medication_no_answer_retry(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "medication_retry", entity_id, idempotency_key)


async def low_stock_notification(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "low_stock", entity_id, idempotency_key)


async def safety_reminder_call(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "safety_reminder", entity_id, idempotency_key)


async def safety_retry(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "safety_retry", entity_id, idempotency_key)


async def safety_escalation(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "safety_escalation", entity_id, idempotency_key)


async def appointment_reminder_call(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "appointment_reminder", entity_id, idempotency_key)


async def appointment_followup_call(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "appointment_followup", entity_id, idempotency_key)


async def family_notification(ctx: dict[str, Any], entity_id: str, idempotency_key: str) -> dict[str, str]:
    return await _run_once(ctx, "family_notification", entity_id, idempotency_key)
