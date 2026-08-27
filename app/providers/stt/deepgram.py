"""Deepgram adapter boundary; live streaming requires an API key and Pipecat wiring."""

from app.domain.exceptions import ProviderUnavailableError


class DeepgramStreamingAdapter:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    async def connect(self) -> None:
        if not self.api_key:
            raise ProviderUnavailableError("Deepgram API key is not configured")
        raise ProviderUnavailableError("Install and configure the live Deepgram/Pipecat transport")
