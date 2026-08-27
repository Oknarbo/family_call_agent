"""High-level outbound voice helpers used by schedulers and internal tools."""

from app.config import Settings, get_settings
from app.providers.telephony.factory import create_telephony_provider
from app.telephony.base import PlacedCall


async def call_mom(
    to_number: str,
    message: str,
    *,
    from_number: str | None = None,
    audio_file_url: str | None = None,
    language: str | None = None,
    settings: Settings | None = None,
) -> PlacedCall:
    """Place an outbound voice call that speaks `message` or plays `audio_file_url`."""

    runtime_settings = settings or get_settings()
    provider = create_telephony_provider(runtime_settings)
    return await provider.place_call(
        to_number,
        message,
        audio_file_url=audio_file_url,
        from_number=from_number,
        language=language,
    )
