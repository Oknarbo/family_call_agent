"""Network boundary only. Dispatch state is committed by scheduler jobs."""

from app.config import Settings
from app.schemas import OutboundCallRecord
from app.telephony.base import PlacedCall
from app.telephony.calls import call_mom


class VoiceDeliveryService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, call: OutboundCallRecord, phone: str) -> PlacedCall:
        return await call_mom(phone, call.message, settings=self.settings, client_reference=str(call.id))
