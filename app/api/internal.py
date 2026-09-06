"""Small authenticated operational surface."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.dependencies import application_store, development_store
from app.domain.enums import OutboundCallStatus
from app.domain.exceptions import DomainError
from app.services.call_outcomes import CallOutcomeService
from app.services.family_directory import FamilyDirectory
from app.telephony.calls import call_mom
from app.utils.datetime import utc_now

router = APIRouter(prefix="/internal", tags=["internal"])


class CallStatusRequest(BaseModel):
    call_id: UUID
    provider_call_id: str = Field(min_length=1, max_length=128)
    status: OutboundCallStatus


class CallResponseRequest(BaseModel):
    call_id: UUID
    outcome: Literal["completed", "taken", "not_taken", "unclear", "call_later"]
    delay_minutes: int | None = Field(default=None, ge=1, le=1440)


@router.post("/call-response")
async def call_response(
    payload: CallResponseRequest, authorization: str | None = Header(default=None)
) -> dict[str, str]:
    """Trusted voice adapter reports explicit user responses, independently of call status."""
    _authorize(authorization)
    try:
        async with application_store() as store:
            CallOutcomeService(store, get_settings()).record_response(
                payload.call_id, payload.outcome, delay_minutes=payload.delay_minutes, now=utc_now()
            )
    except DomainError as exc:
        raise HTTPException(status_code=400, detail=exc.code) from exc
    return {"status": "recorded"}


@router.post("/call-status")
async def call_status(payload: CallStatusRequest, authorization: str | None = Header(default=None)) -> dict[str, str]:
    """Trusted normalized outcomes; future Twilio webhooks must validate signatures first."""
    _authorize(authorization)
    try:
        async with application_store() as store:
            CallOutcomeService(store, get_settings()).record_status(
                payload.call_id, payload.provider_call_id, payload.status, now=utc_now()
            )
    except DomainError as exc:
        raise HTTPException(status_code=400, detail=exc.code) from exc
    return {"status": "recorded"}


@router.get("/scheduler-status")
async def scheduler_status(authorization: str | None = Header(default=None)) -> dict[str, int]:
    """Operational counts without phone numbers or medication details."""
    _authorize(authorization)
    async with application_store() as store:
        return {
            status.value: sum(call.status == status for call in store.outbound_calls.values())
            for status in OutboundCallStatus
        }


def _authorize(value: str | None) -> None:
    settings = get_settings()
    if value != f"Bearer {settings.app_secret_key}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


class TestVoiceCallRequest(BaseModel):
    to_number: str = Field(description="E.164 broj primatelja, npr. +385911234567")
    message: str = Field(min_length=1, max_length=1400)
    from_number: str | None = Field(default=None, description="Opcionalni Infobip sender broj")
    audio_file_url: str | None = Field(default=None, description="Opcionalni javni mp3/wav URL")


@router.delete("/development-data", status_code=status.HTTP_204_NO_CONTENT)
async def delete_development_data(authorization: str | None = Header(default=None)) -> None:
    """Support explicit local data deletion without exposing family data."""

    _authorize(authorization)
    if get_settings().app_env == "production":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="development only")
    development_store().reset()


@router.post("/test-voice-call")
async def test_voice_call(
    payload: TestVoiceCallRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Authenticated smoke test for Infobip outbound voice delivery."""

    _authorize(authorization)
    settings = get_settings()
    try:
        placed = await call_mom(
            payload.to_number,
            payload.message,
            from_number=payload.from_number,
            audio_file_url=payload.audio_file_url,
            settings=settings,
        )
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.user_message) from exc
    return {
        "provider_call_id": placed.provider_call_id,
        "status": placed.status,
    }


class MamaVoiceCallRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1400)
    audio_file_url: str | None = None


@router.post("/test-voice-call/mama")
async def test_voice_call_mama(
    payload: MamaVoiceCallRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    """Call Mama's configured allowlist number with a test message."""

    _authorize(authorization)
    settings = get_settings()
    try:
        async with application_store(settings) as store:
            mama = FamilyDirectory(store).by_name("Mama")
        placed = await call_mom(
            mama.phone_number_e164,
            payload.message,
            audio_file_url=payload.audio_file_url,
            settings=settings,
        )
    except DomainError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=exc.user_message) from exc
    return {
        "target": "Mama",
        "provider_call_id": placed.provider_call_id,
        "status": placed.status,
    }
