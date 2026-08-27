"""Environment-backed application settings."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration; secrets are never committed."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_secret_key: str = "development-only-change-me"
    database_url: str = "sqlite+aiosqlite:///./zvonko-dev.db"
    redis_url: str = "redis://localhost:6379/0"
    default_timezone: str = "Europe/Zagreb"
    assistant_grammatical_gender: Literal["masculine", "feminine"] = "masculine"
    mama_phone_e164: str | None = None
    tata_phone_e164: str | None = None
    branko_phone_e164: str | None = None
    natasa_phone_e164: str | None = None
    llm_provider: str = "development"
    llm_model: str = "deterministic-hr"
    stt_provider: str = "development"
    tts_provider: str = "development"
    telephony_provider: str = "development"
    infobip_base_url: str = "https://api.infobip.com"
    infobip_api_key: str | None = None
    infobip_from_number: str | None = None
    infobip_tts_language: str = "hr"
    public_base_url: str = "http://localhost:8000"
    deepgram_api_key: str | None = None
    store_transcript_summaries: bool = False
    log_level: str = "INFO"
    safety_retry_delays_minutes: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [2, 3])
    safety_escalate_after_no_answers: int = 2
    default_low_stock_threshold: int = 5

    @field_validator("safety_retry_delays_minutes", mode="before")
    @classmethod
    def split_integer_list(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                stripped = stripped[1:-1]
            return [int(item.strip()) for item in stripped.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-in-practice settings object per process."""

    return Settings()
