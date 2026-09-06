"""Direct Deepgram Nova-3 Croatian streaming over 8 kHz mu-law."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from app.domain.exceptions import ProviderUnavailableError

STREAM_URL = (
    "wss://api.deepgram.com/v1/listen?model=nova-3&language=hr"
    "&encoding=mulaw&sample_rate=8000&channels=1&endpointing=1000"
    "&interim_results=false&punctuate=true&mip_opt_out=true"
)


class FinalUtterances:
    """Join final segments and emit once only at the end of an utterance."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.end = -1.0
        self.uncertain = False

    def accept(self, event: dict[str, Any]) -> str | None:
        if event.get("type") != "Results" or not event.get("is_final"):
            return None
        end = float(event.get("start", 0)) + float(event.get("duration", 0))
        if end <= self.end:
            return None
        self.end = end
        alternatives = event.get("channel", {}).get("alternatives", [])
        if alternatives:
            result = alternatives[0]
            text = str(result.get("transcript", "")).strip()
            if text:
                self.parts.append(text)
                self.uncertain |= float(result.get("confidence", 0)) < 0.65
        if sum(map(len, self.parts)) > 2000:
            raise ProviderUnavailableError("Speech turn too long")
        if event.get("speech_final") and self.parts:
            text = "" if self.uncertain else " ".join(self.parts)
            self.parts.clear()
            self.uncertain = False
            return text
        return None


class DeepgramStreamingAdapter:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    async def transcribe(self, audio_chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
        if not self.api_key:
            raise ProviderUnavailableError("Deepgram API key is not configured")
        try:
            async with connect(
                STREAM_URL,
                additional_headers={"Authorization": f"Token {self.api_key}"},
                open_timeout=10,
                close_timeout=3,
                max_size=131072,
            ) as connection:

                async def send() -> None:
                    async for chunk in audio_chunks:
                        await connection.send(chunk)
                    await connection.send(json.dumps({"type": "CloseStream"}))

                async def keepalive() -> None:
                    while True:
                        await asyncio.sleep(4)
                        await connection.send(json.dumps({"type": "KeepAlive"}))

                sender = asyncio.create_task(send())
                keeper = asyncio.create_task(keepalive())
                final = FinalUtterances()
                try:
                    async for raw in connection:
                        event = json.loads(raw)
                        if event.get("type") == "Error":
                            raise ProviderUnavailableError("Deepgram rejected the audio stream")
                        text = final.accept(event)
                        if text is not None:
                            yield text
                finally:
                    sender.cancel()
                    keeper.cancel()
                    for task in (sender, keeper):
                        with suppress(asyncio.CancelledError, Exception):
                            await task
        except asyncio.CancelledError:
            raise
        except InvalidStatus as exc:
            raise ProviderUnavailableError(f"Deepgram returned HTTP {exc.response.status_code}") from None
        except Exception:
            raise ProviderUnavailableError("Deepgram speech connection failed") from None
