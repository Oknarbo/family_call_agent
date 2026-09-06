"""Signed Twilio webhooks and authenticated, single-use media streams."""

import asyncio
import hmac
import json
from contextlib import suppress
from uuid import UUID
from xml.etree.ElementTree import Element, SubElement, tostring

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.config import Settings, get_settings
from app.dependencies import application_store
from app.domain.enums import OutboundCallStatus
from app.domain.exceptions import DomainError
from app.services.call_outcomes import CallOutcomeService
from app.services.family_directory import FamilyDirectory
from app.services.voice_conversation import VoiceConversation, check_outbound
from app.telephony.diagnostics import safe_error
from app.telephony.live_voice import bridge
from app.telephony.twilio_security import (
    media_ticket,
    public_origin,
    read_ticket,
    signature,
    verified_form,
    voice_configured,
)
from app.utils.datetime import utc_now

router = APIRouter(prefix="/twilio", tags=["twilio"])
logger = structlog.get_logger(__name__)


def stream_twiml(settings: Settings, sid: str, phone: str, outbound_id: UUID | None) -> Response:
    root = Element("Response")
    stream = SubElement(
        SubElement(root, "Connect"),
        "Stream",
        {"url": public_origin(settings).replace("https://", "wss://", 1) + "/twilio/media"},
    )
    token = media_ticket(
        settings, {"sid": sid, "phone": phone, "outbound_id": str(outbound_id) if outbound_id else None}
    )
    SubElement(stream, "Parameter", {"name": "ticket", "value": token})
    SubElement(root, "Hangup")
    return Response(tostring(root, encoding="unicode"), media_type="application/xml")


@router.post("/inbound")
async def inbound(request: Request) -> Response:
    settings = get_settings()
    values = await verified_form(request, settings)
    if values.get("To") != settings.twilio_from_number:
        raise HTTPException(403, "Wrong destination")
    try:
        voice_configured(settings)
        async with application_store(settings) as store:
            member = FamilyDirectory(store).identify(values.get("From", ""))
            phone = member.phone_number_e164
    except DomainError:
        return Response('<Response><Reject reason="rejected"/></Response>', media_type="application/xml")
    return stream_twiml(settings, values["CallSid"], phone, None)


@router.post("/outbound/{call_id}")
async def outbound(call_id: UUID, request: Request) -> Response:
    settings = get_settings()
    values = await verified_form(request, settings)
    if values.get("From") != settings.outbound_caller_id:
        raise HTTPException(403, "Wrong sender")
    try:
        voice_configured(settings)
        async with application_store(settings) as store:
            check_outbound(store, call_id, values["CallSid"], values.get("To", ""), settings)
    except (DomainError, ValueError):
        return Response("<Response><Hangup/></Response>", media_type="application/xml")
    return stream_twiml(settings, values["CallSid"], values["To"], call_id)


@router.post("/status/{call_id}", status_code=204)
async def call_status(call_id: UUID, request: Request) -> Response:
    settings = get_settings()
    values = await verified_form(request, settings)
    statuses = {
        "ringing": OutboundCallStatus.RINGING,
        "in-progress": OutboundCallStatus.ANSWERED,
        "completed": OutboundCallStatus.COMPLETED,
        "no-answer": OutboundCallStatus.NO_ANSWER,
        "busy": OutboundCallStatus.BUSY,
        "failed": OutboundCallStatus.FAILED,
        "canceled": OutboundCallStatus.CANCELLED,
    }
    try:
        async with application_store(settings) as store:
            call = store.outbound_calls.get(call_id)
            if call is None:
                raise HTTPException(404, "Unknown call")
            member = store.family_members[call.target_user_id]
            if values.get("To") != member.phone_number_e164 or values.get("From") != settings.outbound_caller_id:
                raise HTTPException(403, "Call association mismatch")
            if call.provider_call_id and call.provider_call_id != values["CallSid"]:
                raise HTTPException(403, "Call identifier mismatch")
            value = values.get("CallStatus", "")
            if value in statuses:
                CallOutcomeService(store, settings).record_status(
                    call_id, values["CallSid"], statuses[value], now=utc_now()
                )
            elif value not in {"queued", "initiated"}:
                raise HTTPException(400, "Unknown call status")
    except DomainError as exc:
        raise HTTPException(400, exc.code) from None
    return Response(status_code=204)


@router.websocket("/media")
async def media(socket: WebSocket) -> None:
    settings = get_settings()
    if settings.telephony_provider != "twilio" or not settings.twilio_auth_token:
        await socket.close(code=1008)
        return
    # Twilio's handshake carries X-Twilio-Signature; use the configured public URL.
    origin = public_origin(settings)
    urls = [origin + "/twilio/media", origin.replace("https://", "wss://", 1) + "/twilio/media"]
    valid = (
        settings.telephony_provider == "twilio"
        and settings.twilio_auth_token
        and any(
            hmac.compare_digest(
                signature(settings.twilio_auth_token, url, []), socket.headers.get("x-twilio-signature", "")
            )
            for url in urls
        )
    )
    if not valid:
        await socket.close(code=1008)
        return
    await socket.accept()
    conversation = None
    stage = "stream_start"
    try:
        voice_configured(settings)
        async with asyncio.timeout(10):
            event = json.loads(await socket.receive_text())
            if event.get("event") == "connected":
                event = json.loads(await socket.receive_text())
            if event.get("event") != "start":
                raise ValueError("Missing stream start")
            start = event["start"]
            data = read_ticket(settings, start.get("customParameters", {}).get("ticket", ""))
            if start.get("accountSid") != settings.twilio_account_sid or start.get("callSid") != data["sid"]:
                raise ValueError("Stream identity mismatch")
            fmt = start.get("mediaFormat", {})
            if fmt.get("encoding") != "audio/x-mulaw" or fmt.get("sampleRate") != 8000 or fmt.get("channels") != 1:
                raise ValueError("Unsupported audio format")
            stage = "redis_stream_claim"
            redis = Redis.from_url(settings.redis_url)
            try:
                claimed = await redis.set("twilio:stream:" + data["sid"], "claimed", nx=True, ex=86400)
            finally:
                await redis.aclose()
            if not claimed:
                raise ValueError("Stream already used")
            conversation = VoiceConversation(
                settings, data["phone"], data["sid"], UUID(data["outbound_id"]) if data["outbound_id"] else None
            )
        stage = "audio_bridge"
        async with asyncio.timeout(settings.voice_max_seconds):
            await bridge(socket, start["streamSid"], conversation)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("voice_session_failed", stage=stage, **safe_error(exc))
        if conversation is not None:
            await conversation.transport_failed()
    finally:
        with suppress(RuntimeError, WebSocketDisconnect):
            await socket.close()
