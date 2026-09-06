"""Provider-neutral telephony interface."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PlacedCall:
    provider_call_id: str
    status: str


class TelephonyProvider(Protocol):
    async def place_call(
        self,
        to_e164: str,
        message: str,
        *,
        audio_file_url: str | None = None,
        from_number: str | None = None,
        language: str | None = None,
        client_reference: str | None = None,
    ) -> PlacedCall: ...
