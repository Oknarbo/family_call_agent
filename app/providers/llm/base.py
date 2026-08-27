"""LLM interface; models never execute application mutations."""

from typing import Protocol


class LanguageUnderstandingProvider(Protocol):
    async def classify_intent(self, utterance: str) -> str: ...
    async def extract_arguments(self, utterance: str, intent: str) -> dict[str, object]: ...
