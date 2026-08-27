"""Fail-closed LLM provider composition."""

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError
from app.providers.llm.base import LanguageUnderstandingProvider
from app.providers.llm.development import DevelopmentLanguageProvider


def create_llm_provider(settings: Settings) -> LanguageUnderstandingProvider:
    if settings.llm_provider == "development":
        return DevelopmentLanguageProvider()
    raise ProviderUnavailableError(f"LLM provider '{settings.llm_provider}' needs a configured adapter")
