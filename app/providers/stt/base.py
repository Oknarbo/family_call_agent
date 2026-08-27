"""Streaming STT contract."""

from collections.abc import AsyncIterator
from typing import Protocol


class StreamingSpeechToText(Protocol):
    async def transcribe(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[str]: ...
