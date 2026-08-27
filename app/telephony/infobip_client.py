"""Infobip Voice Message API client for outbound TTS and audio playback."""

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError, ValidationError

logger = structlog.get_logger(__name__)

INFOBIP_TTS_SINGLE_PATH = "/tts/3/single"


@dataclass(frozen=True, slots=True)
class VoiceMessageResult:
    message_id: str
    status: str
    bulk_id: str | None = None


class InfobipVoiceClient:
    """Low-level HTTP adapter for Infobip single voice TTS / audio messages."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _require_configured(self) -> None:
        if not self.settings.infobip_api_key:
            raise ProviderUnavailableError("Infobip API key is not configured")
        if not self.settings.infobip_from_number:
            raise ProviderUnavailableError("Infobip sender number is not configured")

    @staticmethod
    def _normalize_e164(value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) < 8:
            raise ValidationError("Telefonski broj nije valjan.")
        return digits

    @property
    def _authorization_header(self) -> str:
        api_key = self.settings.infobip_api_key or ""
        if api_key.casefold().startswith("app "):
            return api_key
        return f"App {api_key}"

    @property
    def _base_url(self) -> str:
        return self.settings.infobip_base_url.rstrip("/")

    def _build_payload(
        self,
        *,
        to_e164: str,
        from_number: str | None,
        text: str | None,
        audio_file_url: str | None,
        language: str,
    ) -> dict[str, Any]:
        if text and audio_file_url:
            raise ValidationError("Odaberi ili tekst ili audio URL, ne oboje.")
        if not text and not audio_file_url:
            raise ValidationError("Potreban je tekst poruke ili audio URL.")
        sender = self._normalize_e164(from_number or self.settings.infobip_from_number or "")
        payload: dict[str, Any] = {
            "from": sender,
            "to": self._normalize_e164(to_e164),
        }
        if text:
            payload["text"] = text.strip()
            payload["language"] = language
        else:
            payload["audioFileUrl"] = audio_file_url
        return payload

    async def send_voice_message(
        self,
        to_e164: str,
        *,
        text: str | None = None,
        audio_file_url: str | None = None,
        from_number: str | None = None,
        language: str | None = None,
    ) -> VoiceMessageResult:
        """Send a single outbound voice message via POST /tts/3/single."""

        self._require_configured()
        payload = self._build_payload(
            to_e164=to_e164,
            from_number=from_number,
            text=text,
            audio_file_url=audio_file_url,
            language=language or self.settings.infobip_tts_language,
        )
        url = f"{self._base_url}{INFOBIP_TTS_SINGLE_PATH}"
        log_context = {
            "provider": "infobip",
            "to_suffix": payload["to"][-2:],
            "mode": "tts" if text else "audio_url",
        }
        logger.info("infobip.voice_message.request", **log_context)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": self._authorization_header,
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            logger.exception("infobip.voice_message.transport_error", **log_context)
            raise ProviderUnavailableError("Infobip nije dostupan.") from exc

        if response.status_code >= 400:
            error_text = _extract_error_text(response)
            logger.error(
                "infobip.voice_message.api_error",
                status_code=response.status_code,
                error=error_text,
                **log_context,
            )
            raise ProviderUnavailableError(f"Infobip odbio poziv: {error_text}")

        data = response.json()
        messages = data.get("messages") or []
        if not messages:
            raise ProviderUnavailableError("Infobip nije vratio ID poruke.")
        first = messages[0]
        message_id = str(first.get("messageId") or "")
        status_name = str((first.get("status") or {}).get("name") or "UNKNOWN")
        result = VoiceMessageResult(
            message_id=message_id,
            status=status_name,
            bulk_id=data.get("bulkId"),
        )
        logger.info(
            "infobip.voice_message.accepted",
            message_id=result.message_id,
            status=result.status,
            **log_context,
        )
        return result


def _extract_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200] or f"HTTP {response.status_code}"
    request_error = payload.get("requestError") or {}
    service_exception = request_error.get("serviceException") or {}
    return str(service_exception.get("text") or service_exception.get("messageId") or response.status_code)
