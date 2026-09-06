"""Wire-level audio flow with fake speech services; no real network calls."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from app.config import Settings
from app.telephony.live_voice import bridge


async def test_audio_bridge_waits_for_playback_and_processes_one_response() -> None:
    class Socket:
        def __init__(self) -> None:
            self.events: asyncio.Queue[str] = asyncio.Queue()
            self.sent: list[dict[str, Any]] = []
            self.sequence = 0

        async def receive_text(self) -> str:
            return await self.events.get()

        async def send_json(self, message: dict[str, Any]) -> None:
            self.sent.append(message)
            if message["event"] == "mark":
                self.sequence += 1
                await self.events.put(json.dumps(dict(message, sequenceNumber=str(self.sequence))))

    socket = Socket()

    class Conversation:
        settings = Settings()
        replies: ClassVar[list[str]] = []
        delivered = False

        async def greeting(self) -> str:
            return "Bok"

        async def audio_delivered(self) -> None:
            self.delivered = True
            socket.sequence += 1
            await socket.events.put(
                json.dumps(
                    {
                        "event": "media",
                        "streamSid": "MZ1",
                        "sequenceNumber": str(socket.sequence),
                        "media": {"track": "inbound", "payload": base64.b64encode(b"\x80" * 160).decode()},
                    }
                )
            )

        async def reply(self, text: str) -> tuple[str, bool]:
            assert self.delivered
            self.replies.append(text)
            return "Doviđenja", True

    class Speech:
        async def transcribe(self, chunks: AsyncIterator[bytes]) -> AsyncIterator[str]:
            async for chunk in chunks:
                assert chunk == b"\x80" * 160
                yield "da"

    class Voice:
        async def synthesize_mulaw(self, _text: str) -> bytes:
            return b"\xff" * 160

    conversation = Conversation()
    async with asyncio.timeout(3):
        await bridge(socket, "MZ1", conversation, speech=Speech(), voice=Voice())  # type: ignore[arg-type]
    assert conversation.replies == ["da"]
    assert [m["event"] for m in socket.sent] == ["media", "mark", "media", "mark"]
