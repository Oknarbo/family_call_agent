"""Telephony provider composition."""

from app.config import Settings
from app.domain.exceptions import CallNotPlacedError
from app.providers.telephony.development import DevelopmentTelephonyProvider
from app.providers.telephony.infobip import InfobipTelephonyProvider
from app.providers.telephony.twilio import TwilioTelephonyProvider
from app.telephony.base import TelephonyProvider


def create_telephony_provider(settings: Settings) -> TelephonyProvider:
    if settings.telephony_provider == "development":
        return DevelopmentTelephonyProvider(settings)
    if settings.telephony_provider == "infobip":
        return InfobipTelephonyProvider(settings)
    if settings.telephony_provider == "twilio":
        return TwilioTelephonyProvider(settings)
    raise CallNotPlacedError(f"Telephony provider '{settings.telephony_provider}' is not configured")
