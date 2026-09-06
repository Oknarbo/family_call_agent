"""One conversation turn against the same durable store used by workers."""

from typing import Literal, cast

from app.agent.graph import build_inbound_graph
from app.agent.intents import classify_confirmation
from app.agent.state import ConversationState
from app.config import Settings, get_settings
from app.dependencies import application_store
from app.domain.exceptions import DomainError, ProviderUnavailableError
from app.providers.llm.openai import OpenAILanguageProvider
from app.services.family_directory import FamilyDirectory


async def conversation_turn(state: ConversationState, settings: Settings | None = None) -> ConversationState:
    active = settings or get_settings()
    if active.llm_provider == "openai":
        # Authorize before sending speech to a third party, then release the SQL lock.
        authorized = False
        async with application_store(active) as store:
            try:
                FamilyDirectory(store).identify(state.get("caller_phone", ""))
                authorized = True
            except DomainError:
                pass
            store.abort()
        if authorized:
            pending = state.get("pending_action") or {}
            stage = pending.get("stage")
            mode: Literal["request", "confirmation", "clarification"] = (
                "confirmation"
                if stage == "awaiting_confirmation"
                else "clarification"
                if stage == "clarifying"
                else "request"
            )
            original = state.get("current_utterance", "")
            # Exact confirmations are cheap and do not need a model round trip.
            if mode != "confirmation" or classify_confirmation(original) == "unclear":
                try:
                    normalized = await OpenAILanguageProvider(active).normalize_turn(
                        original, mode=mode, question=str(state.get("response_text") or "")
                    )
                except ProviderUnavailableError:
                    return {
                        **state,
                        "response_text": "Nisam uspio obraditi odgovor. Pokušaj ponovno.",
                        "error_code": "provider_unavailable",
                    }
                if normalized is None:
                    if mode != "confirmation":
                        return {**state, "response_text": "Nisam siguran jesam li razumio. Možeš li ponoviti?"}
                    normalized = "nejasan odgovor"
                state = {**state, "current_utterance": normalized}
    async with application_store(active) as store:
        result = await build_inbound_graph(store, active).ainvoke(state)
        # Graph nodes report domain errors as state instead of raising. Discard
        # all staged writes even if a service mutated records before the error.
        if result.get("error_code"):
            store.abort()
        return cast(ConversationState, result)
