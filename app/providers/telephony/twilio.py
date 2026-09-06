"""Asynchronous Twilio Calls API. A submitted call is never proof of a completed task."""

import re
from uuid import UUID

import httpx

from app.config import Settings
from app.domain.exceptions import CallNotPlacedError, ProviderUnavailableError
from app.telephony.base import PlacedCall
from app.telephony.twilio_security import public_origin, voice_configured


class TwilioTelephonyProvider:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings, self.transport = settings, transport

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
        voice_configured(self.settings)
        if audio_file_url or language not in {None, "hr", "hr-HR"}:
            raise CallNotPlacedError("Twilio calls use the configured Croatian voice session")
        if from_number and from_number != self.settings.outbound_caller_id:
            raise CallNotPlacedError("Sender must match the configured outbound caller ID")
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", to_e164):
            raise CallNotPlacedError("Invalid destination number")
        try:
            reference = str(UUID(client_reference or ""))
        except ValueError:
            raise CallNotPlacedError("Twilio requires a durable outbound call record") from None
        origin = public_origin(self.settings)
        endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{self.settings.twilio_account_sid}/Calls.json"
        # No retries here: a timeout after POST can mean Twilio already accepted the call.
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=15, follow_redirects=False) as client:
                response = await client.post(
                    endpoint,
                    auth=(self.settings.twilio_account_sid or "", self.settings.twilio_auth_token or ""),
                    data={
                        "To": to_e164,
                        "From": self.settings.outbound_caller_id or "",
                        "Url": f"{origin}/twilio/outbound/{reference}",
                        "Method": "POST",
                        "StatusCallback": f"{origin}/twilio/status/{reference}",
                        "StatusCallbackMethod": "POST",
                        "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
                        "Timeout": str(self.settings.twilio_ring_timeout),
                        "TimeLimit": str(self.settings.voice_max_seconds),
                    },
                )
        except httpx.HTTPError:
            raise ProviderUnavailableError("Twilio submission outcome is unknown") from None
        if 400 <= response.status_code < 500 and response.status_code != 408:
            raise CallNotPlacedError(f"Twilio rejected the request (HTTP {response.status_code})")
        if response.status_code != 201:
            raise ProviderUnavailableError("Twilio submission outcome is unknown")
        try:
            data = response.json()
            sid = data["sid"]
            if not isinstance(sid, str) or not re.fullmatch(r"CA[0-9a-fA-F]{32}", sid):
                raise ValueError
            return PlacedCall(sid, str(data.get("status", "queued")))
        except (ValueError, KeyError, TypeError):
            raise ProviderUnavailableError("Twilio returned an invalid call identifier") from None
