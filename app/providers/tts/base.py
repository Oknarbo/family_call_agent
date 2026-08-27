"""Croatian-capable TTS contract."""

from typing import Protocol


class TextToSpeechProvider(Protocol):
    async def synthesize(self, text: str, language: str = "hr-HR") -> bytes: ...
