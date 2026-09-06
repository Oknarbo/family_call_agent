"""TTS composition that never returns fake production audio."""

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError
from app.providers.tts.azure import AzureTextToSpeech
from app.providers.tts.base import TextToSpeechProvider


class DevelopmentTextToSpeech:
    async def synthesize(self, _text: str, language: str = "hr-HR") -> bytes:
        raise ProviderUnavailableError(f"Development TTS has no audio output for {language}")


def create_tts_provider(settings: Settings) -> TextToSpeechProvider:
    if settings.tts_provider == "azure":
        return AzureTextToSpeech(settings)
    if settings.tts_provider == "development":
        return DevelopmentTextToSpeech()
    raise ProviderUnavailableError(f"TTS provider '{settings.tts_provider}' needs configuration")
