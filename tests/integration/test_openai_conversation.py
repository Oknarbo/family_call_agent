import asyncio
from typing import Any

import pytest

from app.config import Settings
from app.dependencies import application_store
from app.domain.exceptions import ProviderUnavailableError
from app.providers.llm.openai import OpenAILanguageProvider
from app.services.voice_conversation import VoiceConversation


async def test_llm_paraphrase_keeps_confirmation_and_releases_sql_lock(
    durable_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = durable_settings.model_copy(update={"llm_provider": "openai"})
    modes = []

    async def normalize(_self: Any, text: str, **kwargs: Any) -> str:
        modes.append(kwargs["mode"])
        async with asyncio.timeout(2), application_store(settings) as store:
            assert not store.reminders
            store.abort()
        return "Podsjeti me za dvije minute da provjerim poštu" if kwargs["mode"] == "request" else "da"

    monkeypatch.setattr(OpenAILanguageProvider, "normalize_turn", normalize)
    conversation = VoiceConversation(settings, "+385910000003", "test-openai")
    await conversation.reply("Možeš li me trgnuti da pogledam poštu za dvije minute?")
    async with application_store(settings) as store:
        assert not store.reminders
    await conversation.reply("Da")
    async with application_store(settings) as store:
        assert len(store.reminders) == 1
    assert modes == ["request"]  # Known approval needs no paid model request.


async def test_unknown_caller_never_reaches_openai(durable_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(*_args: Any, **_kwargs: Any) -> str:
        raise AssertionError("Unauthorized speech was sent to OpenAI")

    monkeypatch.setattr(OpenAILanguageProvider, "normalize_turn", forbidden)
    conversation = VoiceConversation(
        durable_settings.model_copy(update={"llm_provider": "openai"}), "+385910000099", "unknown"
    )
    await conversation.reply("Podsjeti me za dvije minute")
    assert conversation.state.get("caller_is_registered") is False


async def test_provider_failure_preserves_pending_action_without_write(
    durable_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = VoiceConversation(durable_settings, "+385910000003", "pending")
    await conversation.reply("Podsjeti me za dvije minute da provjerim poštu")
    pending = conversation.state["pending_action"]
    conversation.settings = durable_settings.model_copy(update={"llm_provider": "openai"})

    async def fail(*_args: Any, **_kwargs: Any) -> str:
        raise ProviderUnavailableError()

    monkeypatch.setattr(OpenAILanguageProvider, "normalize_turn", fail)
    answer, _ = await conversation.reply("Slažem se s tim")
    assert "Pokušaj ponovno" in answer
    assert conversation.state["pending_action"] == pending
    async with application_store(durable_settings) as store:
        assert not store.reminders
