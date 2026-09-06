"""Signed HTTP requests, real SQL transactions and simulated audio boundaries."""

from datetime import timedelta
from typing import Any, ClassVar
from uuid import UUID
from xml.etree import ElementTree

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import twilio_webhooks
from app.config import Settings
from app.dependencies import application_store
from app.domain.enums import OutboundCallPurpose, OutboundCallStatus, ReminderStatus
from app.main import create_app
from app.scheduler.jobs import scheduler_tick
from app.scheduler.planner import SchedulerPlanner
from app.services.call_outcomes import CallOutcomeService
from app.services.voice_conversation import VoiceConversation
from app.telephony.twilio_security import media_ticket, read_ticket, signature
from app.utils.datetime import utc_now
from tests.integration.test_durable_store import medication, schedule
from tests.unit.test_twilio import configured

SID = "CA" + "2" * 32


async def call_record(settings: Settings, kind: str = "safety") -> tuple[UUID, str]:
    async with application_store(settings) as store:
        if kind == "medication":
            _, entity = medication(store)
            target = store.medication_doses[entity].user_id
            purpose, entity_type = OutboundCallPurpose.MEDICATION_DOSE, "medication_dose"
        else:
            entity = schedule(store)
            target = store.reminders[entity].target_user_id
            purpose, entity_type = OutboundCallPurpose.HOUSEHOLD_SAFETY, "reminder"
        call = SchedulerPlanner(store, settings).ensure_call(
            kind=entity_type,
            entity_id=entity,
            target_id=target,
            due=utc_now(),
            message="test",
            purpose=purpose,
            now=utc_now(),
        )
        call.status = OutboundCallStatus.DIALING
        return call.id, store.family_members[target].phone_number_e164


async def post(client: httpx.AsyncClient, settings: Settings, path: str, values: dict[str, str]) -> httpx.Response:
    headers = {
        "X-Twilio-Signature": signature(
            settings.twilio_auth_token or "", settings.public_base_url + path, list(values.items())
        )
    }
    return await client.post(path, data=values, headers=headers)


@pytest.mark.parametrize("override", [None, "+385910000004"])
async def test_inbound_allowlist_and_signature(
    durable_settings: Settings, monkeypatch: pytest.MonkeyPatch, override: str | None
) -> None:
    settings = configured(database_url=durable_settings.database_url, twilio_outbound_caller_id=override)
    monkeypatch.setattr(twilio_webhooks, "get_settings", lambda: settings)
    form = {
        "AccountSid": settings.twilio_account_sid or "",
        "CallSid": SID,
        "From": "+385910000001",
        "To": settings.twilio_from_number or "",
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://internal") as client:
        assert (await client.post("/twilio/inbound", data=form)).status_code == 403
        response = await post(client, settings, "/twilio/inbound", form)
        assert response.status_code == 200
        root = ElementTree.fromstring(response.text)
        parameter = root.find("Connect/Stream/Parameter")
        assert parameter is not None
        assert read_ticket(settings, parameter.attrib["value"])["phone"] == form["From"]
        response = await post(client, settings, "/twilio/inbound", dict(form, From="+385910000099"))
        assert "Reject" in response.text and "ticket" not in response.text


@pytest.mark.parametrize("override", [None, "+385910000004"])
async def test_signed_no_answer_deduplicates_and_checks_recipient(
    durable_settings: Settings, monkeypatch: pytest.MonkeyPatch, override: str | None
) -> None:
    settings = configured(database_url=durable_settings.database_url, twilio_outbound_caller_id=override)
    monkeypatch.setattr(twilio_webhooks, "get_settings", lambda: settings)
    call_id, phone = await call_record(settings)
    path = f"/twilio/status/{call_id}"
    form = {
        "AccountSid": settings.twilio_account_sid or "",
        "CallSid": SID,
        "From": settings.outbound_caller_id or "",
        "To": phone,
        "CallStatus": "no-answer",
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://internal") as client:
        assert (await post(client, settings, path, dict(form, To="+385910000099"))).status_code == 403
        for _ in range(2):
            assert (await post(client, settings, path, form)).status_code == 204
        assert (await post(client, settings, path, dict(form, CallSid="CA" + "3" * 32))).status_code == 403
    async with application_store(settings) as store:
        assert len(store.outbound_calls) == 2
        assert store.outbound_calls[call_id].status == OutboundCallStatus.NO_ANSWER


async def test_spoken_medication_and_snooze_are_durable(durable_settings: Settings) -> None:
    settings = configured(database_url=durable_settings.database_url)
    call_id, phone = await call_record(settings, "medication")
    async with application_store(settings) as store:
        CallOutcomeService(store, settings).record_status(call_id, SID, OutboundCallStatus.ANSWERED, now=utc_now())
    conversation = VoiceConversation(settings, phone, SID, call_id)
    assert "tabletu" in await conversation.greeting()
    await conversation.reply("Ne znam jesam li popila")
    async with application_store(settings) as store:
        assert next(iter(store.medication_plans.values())).current_inventory == 2
    answer, done = await conversation.reply("Popila sam tabletu")
    assert "Zabilježio" in answer and done
    async with application_store(settings) as store:
        assert next(iter(store.medication_plans.values())).current_inventory == 1
        CallOutcomeService(store, settings).record_response(call_id, "taken", now=utc_now())
        assert next(iter(store.medication_plans.values())).current_inventory == 1


async def test_safety_snooze_uses_minutes_and_never_completes(durable_settings: Settings) -> None:
    settings = configured(database_url=durable_settings.database_url)
    call_id, phone = await call_record(settings)
    async with application_store(settings) as store:
        CallOutcomeService(store, settings).record_status(call_id, SID, OutboundCallStatus.ANSWERED, now=utc_now())
    conversation = VoiceConversation(settings, phone, SID, call_id)
    await conversation.reply("Nisam ugasila plin")
    before = utc_now()
    answer, done = await conversation.reply("Nazovi me za petnaest minuta")
    assert done and "15 minuta" in answer
    async with application_store(settings) as store:
        assert store.outbound_calls[call_id].user_outcome == "call_later"
        retry = next(c for c in store.outbound_calls.values() if c.id != call_id)
        assert before + timedelta(minutes=15) <= retry.scheduled_for < before + timedelta(minutes=16)
        assert next(iter(store.reminders.values())).status != ReminderStatus.COMPLETED


async def test_inbound_confirmation_and_disconnection(durable_settings: Settings) -> None:
    conversation = VoiceConversation(durable_settings, "+385910000003", SID)
    await conversation.reply("Podsjeti me za petnaest minuta da se pripremim za razgovor za posao")
    async with application_store(durable_settings) as store:
        assert not store.reminders
    # Reconnecting does not reuse an abandoned pending confirmation.
    await VoiceConversation(durable_settings, "+385910000003", SID + "x").reply("Da")
    async with application_store(durable_settings) as store:
        assert not store.reminders
    await conversation.reply("Da")
    async with application_store(durable_settings) as store:
        assert len(store.reminders) == 1


@pytest.mark.parametrize("confirmation", ["Da, da.", "Točno.", "Potvrdujem."])
async def test_inbound_spoken_confirmation(durable_settings: Settings, confirmation: str) -> None:
    conversation = VoiceConversation(durable_settings, "+385910000003", SID)
    await conversation.reply("Podsjeti me za dvije minute da provjerim poštu")
    answer, _ = await conversation.reply(confirmation)
    assert answer == "Dogovoreno."
    async with application_store(durable_settings) as store:
        assert len(store.reminders) == 1


@pytest.mark.parametrize("confirmation", ["Da, da.", "Točno.", "Potvrđujem."])
async def test_general_outbound_accepts_same_confirmations(durable_settings: Settings, confirmation: str) -> None:
    settings = configured(database_url=durable_settings.database_url)
    call_id, phone = await call_record(settings)
    async with application_store(settings) as store:
        store.outbound_calls[call_id].purpose = OutboundCallPurpose.GENERAL_REMINDER
        CallOutcomeService(store, settings).record_status(call_id, SID, OutboundCallStatus.ANSWERED, now=utc_now())
    answer, done = await VoiceConversation(settings, phone, SID, call_id).reply(confirmation)
    assert done and "zabilježeno" in answer
    async with application_store(settings) as store:
        assert store.outbound_calls[call_id].user_outcome == "completed"


async def test_outbound_unclear_answers_are_bounded(durable_settings: Settings) -> None:
    settings = configured(database_url=durable_settings.database_url)
    call_id, phone = await call_record(settings, "medication")
    async with application_store(settings) as store:
        CallOutcomeService(store, settings).record_status(call_id, SID, OutboundCallStatus.ANSWERED, now=utc_now())
    conversation = VoiceConversation(settings, phone, SID, call_id)
    for _ in range(3):
        answer, done = await conversation.reply("potvrđujem")
    assert done and "Nisam zabilježio potvrdu" in answer
    async with application_store(settings) as store:
        assert store.outbound_calls[call_id].user_outcome == "unclear"


async def test_unclear_confirmations_stop_without_saving(durable_settings: Settings) -> None:
    conversation = VoiceConversation(durable_settings, "+385910000003", SID)
    await conversation.reply("Podsjeti me za dvije minute da provjerim poštu")
    for _ in range(3):
        answer, _ = await conversation.reply("Možda")
    assert "nije spremljen" in answer
    assert conversation.state.get("pending_action") is None
    async with application_store(durable_settings) as store:
        assert not store.reminders


async def test_twilio_completion_without_audio_is_not_delivery(durable_settings: Settings) -> None:
    settings = configured(database_url=durable_settings.database_url)
    call_id, phone = await call_record(settings)
    async with application_store(settings) as store:
        call = store.outbound_calls[call_id]
        call.purpose = OutboundCallPurpose.GENERAL_REMINDER
        CallOutcomeService(store, settings).record_status(call_id, SID, OutboundCallStatus.COMPLETED, now=utc_now())
        assert store.reminders[call.related_entity_id].status != ReminderStatus.COMPLETED
    await VoiceConversation(settings, phone, SID, call_id).audio_delivered()
    async with application_store(settings) as store:
        assert next(iter(store.reminders.values())).status == ReminderStatus.COMPLETED


async def test_automatic_outbound_is_paused_by_default(durable_settings: Settings) -> None:
    settings = configured(database_url=durable_settings.database_url)
    assert (await scheduler_tick({"settings": settings}))["paused"] == 1


def test_media_handshake_requires_signature_and_single_use_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = configured()
    monkeypatch.setattr(twilio_webhooks, "get_settings", lambda: settings)

    class FakeRedis:
        used: ClassVar[set[str]] = set()

        async def set(self, key: str, _value: str, **_kwargs: Any) -> bool:
            if key in self.used:
                return False
            self.used.add(key)
            return True

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(twilio_webhooks.Redis, "from_url", lambda _url: FakeRedis())

    async def fake_bridge(socket: Any, stream_id: str, conversation: Any) -> None:
        assert stream_id == "MZ1"
        assert conversation.caller_phone == "+385910000001"
        await socket.send_json({"accepted": True})

    monkeypatch.setattr(twilio_webhooks, "bridge", fake_bridge)
    token = media_ticket(settings, {"sid": SID, "phone": "+385910000001", "outbound_id": None})
    start = {
        "event": "start",
        "start": {
            "callSid": SID,
            "accountSid": settings.twilio_account_sid,
            "streamSid": "MZ1",
            "customParameters": {"ticket": token},
            "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1},
        },
    }
    signed = signature(settings.twilio_auth_token or "", settings.public_base_url + "/twilio/media", [])
    with TestClient(create_app()) as client:
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/twilio/media"):
            pass
        with client.websocket_connect("/twilio/media", headers={"x-twilio-signature": signed}) as socket:
            socket.send_json(start)
            assert socket.receive_json() == {"accepted": True}
        with client.websocket_connect("/twilio/media", headers={"x-twilio-signature": signed}) as socket:
            socket.send_json(start)
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()
