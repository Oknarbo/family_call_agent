"""Explicitly disabled development transport; never fall back to a paid provider."""

from app.config import Settings
from app.domain.exceptions import CallNotPlacedError
from app.telephony.base import PlacedCall


class DevelopmentTelephonyProvider:
    provider_name = "development-only"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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
        raise CallNotPlacedError("Outbound voice is disabled in development")
