"""Infobip-backed telephony provider."""

from app.config import Settings
from app.telephony.base import PlacedCall
from app.telephony.infobip_client import InfobipVoiceClient


class InfobipTelephonyProvider:
    provider_name = "infobip"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = InfobipVoiceClient(settings)

    async def place_call(
        self,
        to_e164: str,
        message: str,
        *,
        audio_file_url: str | None = None,
        from_number: str | None = None,
        language: str | None = None,
        client_reference: str | None = None,
    ) -> PlacedCall:
        result = await self.client.send_voice_message(
            to_e164,
            text=message if not audio_file_url else None,
            audio_file_url=audio_file_url,
            from_number=from_number,
            language=language,
        )
        return PlacedCall(provider_call_id=result.message_id, status=result.status)
