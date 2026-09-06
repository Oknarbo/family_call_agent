"""Whole scheduler lifecycle with real SQL and simulated network boundaries."""

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.dependencies import application_store
from app.domain.enums import MedicationDoseStatus, OutboundCallStatus, ReminderStatus
from app.domain.exceptions import CallNotPlacedError, ValidationError
from app.scheduler.jobs import dispatch_outbound_call, scheduler_tick
from app.services.call_outcomes import CallOutcomeService
from app.services.family_directory import FamilyDirectory
from app.telephony.base import PlacedCall
from app.utils.datetime import utc_now
from tests.integration.test_durable_store import medication, schedule


class Queue:
    def __init__(self) -> None:
        self.jobs: dict[str, tuple[str, str, dict[str, Any]]] = {}

    async def enqueue_job(self, name: str, entity_id: str, **kwargs: Any) -> object | None:
        key = kwargs["_job_id"]
        if key in self.jobs:
            return None
        self.jobs[key] = (name, entity_id, kwargs)
        return object()


class Voice:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sent: list[UUID] = []

    async def send(self, call: Any, phone: str) -> PlacedCall:
        # This would time out if dispatch held the SQL lock during network I/O.
        async with asyncio.timeout(2), application_store(self.settings) as store:
            assert store.outbound_calls[call.id].status == OutboundCallStatus.DIALING
            assert FamilyDirectory(store).by_id(call.target_user_id).phone_number_e164 == phone
        self.sent.append(call.id)
        return PlacedCall(provider_call_id=f"provider-{call.id}", status="accepted")


async def prepare(settings: Settings, kind: str = "safety") -> tuple[dict[str, Any], UUID]:
    now = utc_now().replace(second=0, microsecond=0)
    ctx: dict[str, Any] = {"settings": settings, "redis": Queue(), "now": now, "voice_delivery": Voice(settings)}
    async with application_store(settings) as store:
        if kind == "medication":
            plan_id, entity_id = medication(store)
            plan = store.medication_plans[plan_id]
            plan.created_at = now - timedelta(days=1)
            plan.local_schedule_time = now.astimezone(ZoneInfo(plan.timezone)).time()
            store.medication_doses[entity_id].scheduled_for = now
        else:
            entity_id = schedule(store)
            store.reminders[entity_id].scheduled_for = now
    await scheduler_tick(ctx)
    return ctx, entity_id


async def next_call(settings: Settings) -> Any:
    async with application_store(settings) as store:
        return min(
            (c for c in store.outbound_calls.values() if c.status == OutboundCallStatus.SCHEDULED),
            key=lambda c: c.scheduled_for,
        )


async def finish(ctx: dict[str, Any], call: Any, status: OutboundCallStatus) -> None:
    ctx["now"] = max(ctx["now"], call.scheduled_for)
    await dispatch_outbound_call(ctx, str(call.id))
    ctx["now"] += timedelta(seconds=10)
    async with application_store(ctx["settings"]) as store:
        CallOutcomeService(store, ctx["settings"]).record_status(call.id, f"provider-{call.id}", status, now=ctx["now"])


@pytest.mark.parametrize("kind", ["safety", "medication"])
async def test_no_answer_chain_survives_restarts(durable_settings: Settings, kind: str) -> None:
    ctx, entity_id = await prepare(durable_settings, kind)
    first = await next_call(durable_settings)
    await finish(ctx, first, OutboundCallStatus.NO_ANSWER)
    retry = await next_call(durable_settings)
    assert retry.target_user_id == first.target_user_id
    assert retry.scheduled_for == ctx["now"] + timedelta(minutes=2)
    async with application_store(durable_settings) as store:
        # Duplicate callback creates neither another retry nor a family call.
        CallOutcomeService(store, durable_settings).record_status(
            first.id, f"provider-{first.id}", OutboundCallStatus.NO_ANSWER, now=ctx["now"]
        )
        assert len(store.outbound_calls) == 2
    await finish(ctx, retry, OutboundCallStatus.NO_ANSWER)
    branko = await next_call(durable_settings)
    async with application_store(durable_settings) as store:
        assert branko.target_user_id == FamilyDirectory(store).by_name("Branko").id
    await finish(ctx, branko, OutboundCallStatus.NO_ANSWER)
    natasa = await next_call(durable_settings)
    async with application_store(durable_settings) as store:
        assert natasa.target_user_id == FamilyDirectory(store).by_name("Nataša").id
    await finish(ctx, natasa, OutboundCallStatus.NO_ANSWER)
    await scheduler_tick(ctx)
    async with application_store(durable_settings) as store:
        assert len(store.outbound_calls) == 4
        assert not any(c.status == OutboundCallStatus.SCHEDULED for c in store.outbound_calls.values())
        if kind == "medication":
            dose = store.medication_doses[entity_id]
            assert dose.status == MedicationDoseStatus.NO_ANSWER
            assert store.medication_plans[dose.medication_plan_id].current_inventory == 2
        else:
            assert store.reminders[entity_id].status != ReminderStatus.COMPLETED


async def test_acceptance_is_not_completion_and_dispatch_is_single(durable_settings: Settings) -> None:
    ctx, entity_id = await prepare(durable_settings)
    call = await next_call(durable_settings)
    results = await asyncio.gather(dispatch_outbound_call(ctx, str(call.id)), dispatch_outbound_call(ctx, str(call.id)))
    assert {result["status"] for result in results} == {"submitted", "duplicate_skipped"}
    assert ctx["voice_delivery"].sent == [call.id]
    async with application_store(durable_settings) as store:
        assert store.reminders[entity_id].status == ReminderStatus.EXECUTING
        assert store.outbound_calls[call.id].status == OutboundCallStatus.DIALING
    await finish(ctx, call, OutboundCallStatus.COMPLETED)
    async with application_store(durable_settings) as store:
        assert store.reminders[entity_id].status != ReminderStatus.COMPLETED


async def test_no_early_or_cancelled_call(durable_settings: Settings) -> None:
    ctx, entity_id = await prepare(durable_settings)
    call = await next_call(durable_settings)
    ctx["now"] = call.scheduled_for - timedelta(seconds=1)
    assert (await dispatch_outbound_call(ctx, str(call.id)))["status"] == "not_due"
    async with application_store(durable_settings) as store:
        store.reminders[entity_id].status = ReminderStatus.CANCELLED
    ctx["now"] = call.scheduled_for
    assert (await dispatch_outbound_call(ctx, str(call.id)))["status"] == "cancelled"
    assert ctx["voice_delivery"].sent == []


async def test_redis_loss_recovers_same_call(durable_settings: Settings) -> None:
    ctx, _ = await prepare(durable_settings)
    original = dict(ctx["redis"].jobs)
    ctx["redis"] = Queue()
    await scheduler_tick(ctx)
    assert ctx["redis"].jobs == original
    async with application_store(durable_settings) as store:
        assert len(store.outbound_calls) == 1


async def test_redis_failure_does_not_lose_sql_work(durable_settings: Settings) -> None:
    ctx, _ = await prepare(durable_settings)

    class BrokenQueue:
        async def enqueue_job(self, *args: Any, **kwargs: Any) -> None:
            raise ConnectionError("simulated redis outage")

    ctx["redis"] = BrokenQueue()
    with pytest.raises(ConnectionError):
        await scheduler_tick(ctx)
    ctx["redis"] = Queue()
    assert (await scheduler_tick(ctx))["queued"] == 1


@pytest.mark.parametrize("known", [True, False])
async def test_provider_failure_is_not_no_answer(durable_settings: Settings, known: bool) -> None:
    ctx, _ = await prepare(durable_settings)
    call = await next_call(durable_settings)

    class BrokenVoice:
        async def send(self, *args: Any) -> None:
            if known:
                raise CallNotPlacedError()
            raise TimeoutError("provider may have accepted")

    ctx["voice_delivery"] = BrokenVoice()
    result = await dispatch_outbound_call(ctx, str(call.id))
    assert result["status"] == ("failed" if known else "delivery_unknown")
    await scheduler_tick(ctx)
    async with application_store(durable_settings) as store:
        assert len(store.outbound_calls) == 1
        assert store.outbound_calls[call.id].status != OutboundCallStatus.NO_ANSWER


async def test_stale_claim_is_not_redialled(durable_settings: Settings) -> None:
    ctx, _ = await prepare(durable_settings)
    call = await next_call(durable_settings)
    async with application_store(durable_settings) as store:
        c = store.outbound_calls[call.id]
        c.status, c.started_at = OutboundCallStatus.DIALING, ctx["now"] - timedelta(minutes=20)
    await scheduler_tick(ctx)
    assert (await dispatch_outbound_call(ctx, str(call.id)))["status"] == "duplicate_skipped"
    assert not ctx["voice_delivery"].sent
    async with application_store(durable_settings) as store:
        assert store.outbound_calls[call.id].status == OutboundCallStatus.DELIVERY_UNKNOWN


async def test_explicit_taken_deducts_once_and_snooze_keeps_stock(durable_settings: Settings) -> None:
    ctx, dose_id = await prepare(durable_settings, "medication")
    first = await next_call(durable_settings)
    await finish(ctx, first, OutboundCallStatus.ANSWERED)
    async with application_store(durable_settings) as store:
        CallOutcomeService(store, durable_settings).record_response(
            first.id, "call_later", now=ctx["now"], delay_minutes=15
        )
        assert store.medication_plans[store.medication_doses[dose_id].medication_plan_id].current_inventory == 2
    await finish(ctx, first, OutboundCallStatus.COMPLETED)
    retry = await next_call(durable_settings)
    await finish(ctx, retry, OutboundCallStatus.ANSWERED)
    async with application_store(durable_settings) as store:
        CallOutcomeService(store, durable_settings).record_response(retry.id, "taken", now=ctx["now"])
    async with application_store(durable_settings) as store:
        CallOutcomeService(store, durable_settings).record_response(retry.id, "taken", now=ctx["now"])
        assert store.medication_doses[dose_id].status == MedicationDoseStatus.USER_REPORTED_TAKEN
        assert store.medication_plans[store.medication_doses[dose_id].medication_plan_id].current_inventory == 1


async def test_late_callbacks_and_wrong_provider_id(durable_settings: Settings) -> None:
    ctx, _ = await prepare(durable_settings)
    call = await next_call(durable_settings)
    await finish(ctx, call, OutboundCallStatus.ANSWERED)
    with pytest.raises(ValidationError):
        async with application_store(durable_settings) as store:
            CallOutcomeService(store, durable_settings).record_status(
                call.id, "wrong", OutboundCallStatus.NO_ANSWER, now=ctx["now"]
            )
    async with application_store(durable_settings) as store:
        service = CallOutcomeService(store, durable_settings)
        service.record_status(call.id, f"provider-{call.id}", OutboundCallStatus.NO_ANSWER, now=ctx["now"])
        assert store.outbound_calls[call.id].status == OutboundCallStatus.ANSWERED
        assert len(store.outbound_calls) == 1


async def test_callback_before_send_returns_is_not_overwritten(durable_settings: Settings) -> None:
    ctx, _ = await prepare(durable_settings)
    call = await next_call(durable_settings)

    class FastCallbackVoice:
        async def send(self, snapshot: Any, phone: str) -> PlacedCall:
            async with application_store(durable_settings) as store:
                CallOutcomeService(store, durable_settings).record_status(
                    snapshot.id, "fast-provider", OutboundCallStatus.NO_ANSWER, now=ctx["now"]
                )
            return PlacedCall("fast-provider", "accepted")

    ctx["voice_delivery"] = FastCallbackVoice()
    await dispatch_outbound_call(ctx, str(call.id))
    async with application_store(durable_settings) as store:
        assert store.outbound_calls[call.id].status == OutboundCallStatus.NO_ANSWER
        assert len(store.outbound_calls) == 2


async def test_medication_explicit_hour_snooze_is_honored(durable_settings: Settings) -> None:
    ctx, _ = await prepare(durable_settings, "medication")
    call = await next_call(durable_settings)
    await finish(ctx, call, OutboundCallStatus.ANSWERED)
    async with application_store(durable_settings) as store:
        CallOutcomeService(store, durable_settings).record_response(
            call.id, "call_later", now=ctx["now"], delay_minutes=60
        )
    await finish(ctx, call, OutboundCallStatus.COMPLETED)
    retry = await next_call(durable_settings)
    ctx["now"] = retry.scheduled_for
    await scheduler_tick(ctx)
    result = await dispatch_outbound_call(ctx, str(retry.id))
    assert result["status"] == "submitted"
    await scheduler_tick(ctx)
    await finish(ctx, retry, OutboundCallStatus.ANSWERED)
    async with application_store(durable_settings) as store:
        CallOutcomeService(store, durable_settings).record_response(retry.id, "taken", now=ctx["now"])
        assert store.medication_doses[retry.related_entity_id].status == MedicationDoseStatus.USER_REPORTED_TAKEN


async def test_same_recipient_calls_do_not_overlap(durable_settings: Settings) -> None:
    ctx, _ = await prepare(durable_settings)
    first = await next_call(durable_settings)
    async with application_store(durable_settings) as store:
        reminder_id = schedule(store, "second")
        store.reminders[reminder_id].scheduled_for = ctx["now"]
    await scheduler_tick(ctx)
    await dispatch_outbound_call(ctx, str(first.id))
    second = await next_call(durable_settings)
    assert (await dispatch_outbound_call(ctx, str(second.id)))["status"] == "recipient_busy"
    await finish(ctx, first, OutboundCallStatus.COMPLETED)
    assert (await dispatch_outbound_call(ctx, str(second.id)))["status"] == "submitted"


async def test_unclear_medication_response_can_be_clarified(durable_settings: Settings) -> None:
    ctx, dose_id = await prepare(durable_settings, "medication")
    call = await next_call(durable_settings)
    await finish(ctx, call, OutboundCallStatus.ANSWERED)
    async with application_store(durable_settings) as store:
        CallOutcomeService(store, durable_settings).record_response(call.id, "unclear", now=ctx["now"])
    async with application_store(durable_settings) as store:
        CallOutcomeService(store, durable_settings).record_response(call.id, "taken", now=ctx["now"])
        assert store.medication_doses[dose_id].status == MedicationDoseStatus.USER_REPORTED_TAKEN
        plan_id = store.medication_doses[dose_id].medication_plan_id
        assert store.medication_plans[plan_id].current_inventory == 1
