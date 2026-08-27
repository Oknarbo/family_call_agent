"""Live Pipecat pipeline integration boundary."""

from dataclasses import dataclass

from app.domain.exceptions import ProviderUnavailableError


@dataclass(slots=True)
class DevelopmentVoicePipeline:
    """Explicitly non-production placeholder; it never pretends to stream audio."""

    provider_name: str = "development-only"

    async def start(self, _call_id: str) -> None:
        raise ProviderUnavailableError("Live audio requires configured Pipecat providers")
