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
    sven_phone_e164: str | None = None
    llm_provider: str = "development"
    llm_model: str = "deterministic-hr"
    stt_provider: str = "development"
    tts_provider: str = "development"
    telephony_provider: str = "development"
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    twilio_outbound_caller_id: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{7,14}$")
    twilio_ring_timeout: int = Field(default=30, ge=5, le=60)
    twilio_outbound_enabled: bool = False
    azure_speech_key: str | None = None
    azure_speech_region: str = Field(default="westeurope", pattern=r"^[a-z0-9]+$")
    azure_speech_voice: Literal["hr-HR-SreckoNeural", "hr-HR-GabrijelaNeural"] = "hr-HR-SreckoNeural"
    azure_speech_rate_percent: int = Field(default=-10, ge=-30, le=20)
    voice_max_seconds: int = Field(default=600, ge=60, le=1800)
    infobip_base_url: str = "https://api.infobip.com"
    infobip_api_key: str | None = None
    infobip_from_number: str | None = None
    infobip_tts_language: str = "hr"
    public_base_url: str = "http://localhost:8000"
    deepgram_api_key: str | None = None
    store_transcript_summaries: bool = False
    log_level: str = "INFO"
    safety_retry_delays_minutes: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [2, 3])
    safety_escalate_after_no_answers: int = Field(default=2, ge=1, le=5)
    default_low_stock_threshold: int = 5
    scheduler_lookahead_minutes: int = Field(default=60, ge=1, le=1440)
    scheduler_batch_size: int = Field(default=100, ge=1, le=1000)
    scheduler_stale_call_seconds: int = Field(default=600, ge=120)
    medication_catchup_minutes: int = Field(default=30, ge=1, le=120)
    medication_no_answer_attempts: int = Field(default=2, ge=1, le=5)
    medication_retry_minutes: int = Field(default=2, ge=1, le=30)
    general_no_answer_attempts: int = Field(default=2, ge=1, le=5)
    general_retry_minutes: int = Field(default=5, ge=1, le=60)
    max_user_call_attempts: int = Field(default=5, ge=1, le=10)

    @property
    def outbound_caller_id(self) -> str | None:
        """Verified outbound identity; the inbound Twilio number stays separate."""
        return self.twilio_outbound_caller_id or self.twilio_from_number

    @field_validator("twilio_outbound_caller_id", mode="before")
    @classmethod
    def empty_caller_id(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("safety_retry_delays_minutes", mode="before")
    @classmethod
    def split_integer_list(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                stripped = stripped[1:-1]
            return [int(item.strip()) for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("safety_retry_delays_minutes")
    @classmethod
    def positive_retry_delays(cls, value: list[int]) -> list[int]:
        if any(delay < 1 or delay > 60 for delay in value):
            raise ValueError("Retry delays must be between 1 and 60 minutes")
        return value


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-in-practice settings object per process."""

    return Settings()
