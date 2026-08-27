"""Development telephony provider that never pretends a live call succeeded."""

import structlog

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError
from app.telephony.base import PlacedCall

logger = structlog.get_logger(__name__)


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
    ) -> PlacedCall:
        if self.settings.infobip_api_key and self.settings.infobip_from_number:
            from app.providers.telephony.infobip import InfobipTelephonyProvider

            logger.info(
                "telephony.development_fallback_to_infobip",
                to_suffix=to_e164[-2:],
            )
            return await InfobipTelephonyProvider(self.settings).place_call(
                to_e164,
                message,
                audio_file_url=audio_file_url,
                from_number=from_number,
                language=language,
            )
        logger.warning(
            "telephony.development_skipped",
            to_suffix=to_e164[-2:],
            has_audio=audio_file_url is not None,
        )
        raise ProviderUnavailableError(
            "Outbound voice is disabled in development. Set TELEPHONY_PROVIDER=infobip and Infobip credentials."
        )
