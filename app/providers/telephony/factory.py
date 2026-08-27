"""Telephony provider composition."""

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError
from app.providers.telephony.development import DevelopmentTelephonyProvider
from app.providers.telephony.infobip import InfobipTelephonyProvider
from app.telephony.base import TelephonyProvider


def create_telephony_provider(settings: Settings) -> TelephonyProvider:
    if settings.telephony_provider == "development":
        return DevelopmentTelephonyProvider(settings)
    if settings.telephony_provider == "infobip":
        return InfobipTelephonyProvider(settings)
    raise ProviderUnavailableError(
        f"Telephony provider '{settings.telephony_provider}' is not configured"
    )
