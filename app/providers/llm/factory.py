"""Fail-closed LLM provider composition."""

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError
from app.providers.llm.base import LanguageUnderstandingProvider
from app.providers.llm.development import DevelopmentLanguageProvider
from app.providers.llm.openai import OpenAILanguageProvider


def create_llm_provider(settings: Settings) -> LanguageUnderstandingProvider:
    if settings.llm_provider == "development":
        return DevelopmentLanguageProvider()
    if settings.llm_provider == "openai":
        return OpenAILanguageProvider(settings)
    raise ProviderUnavailableError(f"LLM provider '{settings.llm_provider}' needs a configured adapter")
