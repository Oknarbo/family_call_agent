"""Deterministic, credentials-free language provider."""

from app.agent.intents import classify_intent


class DevelopmentLanguageProvider:
    provider_name = "development-only-deterministic"

    async def classify_intent(self, utterance: str) -> str:
        return classify_intent(utterance).value

    async def extract_arguments(self, _utterance: str, _intent: str) -> dict[str, object]:
        return {}
