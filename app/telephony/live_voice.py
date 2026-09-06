"""Bounded half-duplex Twilio audio bridge. No raw audio is written to disk."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import WebSocket

from app.providers.stt.deepgram import DeepgramStreamingAdapter
from app.providers.tts.azure import AzureTextToSpeech
from app.services.voice_conversation import VoiceConversation


async def bridge(
    socket: WebSocket,
    stream_id: str,
    conversation: VoiceConversation,
    *,
    speech: DeepgramStreamingAdapter | None = None,
    voice: AzureTextToSpeech | None = None,
) -> None:
    speech = speech or DeepgramStreamingAdapter(conversation.settings.deepgram_api_key)
    voice = voice or AzureTextToSpeech(conversation.settings)
    audio: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
    utterances: asyncio.Queue[str] = asyncio.Queue(maxsize=4)
    played = asyncio.Event()
    current_mark = ""
    speaking = True
    last_sequence = -1

    async def chunks() -> AsyncIterator[bytes]:
        while True:
            yield await audio.get()

    async def receive() -> None:
        nonlocal last_sequence
        while True:
            raw = await socket.receive_text()
            if len(raw) > 16384:
                raise ValueError("Media frame too large")
            event = json.loads(raw)
            if event.get("streamSid") != stream_id:
                raise ValueError("Stream mismatch")
            sequence = int(event.get("sequenceNumber", 0))
            if sequence <= last_sequence:
                continue
            last_sequence = sequence
            if event.get("event") == "stop":
                return
            if event.get("event") == "mark" and event.get("mark", {}).get("name") == current_mark:
                played.set()
            elif event.get("event") == "media":
                media = event["media"]
                if media.get("track") != "inbound":
                    continue
                payload = base64.b64decode(media["payload"], validate=True)
                if not payload or len(payload) > 8000:
                    raise ValueError("Invalid audio frame")
                # First pilot is half duplex. Send silence during playback so
                # echoed prompts cannot be classified as the person's answer.
                audio.put_nowait(b"\xff" * len(payload) if speaking else payload)

    async def recognize() -> None:
        async for text in speech.transcribe(chunks()):
            if not speaking:
                utterances.put_nowait(text)
        raise ValueError("Speech connection ended")

    async def speak(text: str) -> None:
        nonlocal current_mark, speaking
        speaking = True
        played.clear()
        current_mark = uuid4().hex
        pcm = await voice.synthesize_mulaw(text)
        for offset in range(0, len(pcm), 16000):
            await socket.send_json(
                {
                    "event": "media",
                    "streamSid": stream_id,
                    "media": {"payload": base64.b64encode(pcm[offset : offset + 16000]).decode()},
                }
            )
        await socket.send_json({"event": "mark", "streamSid": stream_id, "mark": {"name": current_mark}})
        await asyncio.wait_for(played.wait(), timeout=len(pcm) / 8000 + 10)
        while not utterances.empty():
            utterances.get_nowait()
        speaking = False

    async def dialogue() -> None:
        nonlocal speaking
        await speak(await conversation.greeting())
        await conversation.audio_delivered()
        for _ in range(30):
            try:
                text = await asyncio.wait_for(utterances.get(), timeout=45)
            except TimeoutError:
                await speak("Nisam čuo odgovor. Ništa novo nisam potvrdio. Doviđenja.")
                return
            speaking = True
            answer, finished = await conversation.reply(text)
            await speak(answer)
            if finished:
                return
        await speak("Razgovor je završen. Možeš me ponovno nazvati. Doviđenja.")

    tasks = [asyncio.create_task(action()) for action in (receive, recognize, dialogue)]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
