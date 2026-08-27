"""Small authenticated operational surface."""

from pydantic import BaseModel, Field

from fastapi import APIRouter, Header, HTTPException, status

from app.config import get_settings
from app.dependencies import development_store
from app.domain.exceptions import DomainError
from app.services.family_directory import FamilyDirectory
from app.telephony.calls import call_mom

router = APIRouter(prefix="/internal", tags=["internal"])


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
    mama = FamilyDirectory(development_store()).by_name("Mama")
    try:
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
