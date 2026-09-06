"""Probe speech services and Redis without calling anyone or saving audio.

Azure generates one short fixed sentence; Deepgram opens one short connection.
These checks may consume a small amount of the providers' quota.
"""

import asyncio
import json

from redis.asyncio import Redis
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from app.config import Settings, get_settings
from app.domain.exceptions import ProviderUnavailableError
from app.providers.stt.deepgram import STREAM_URL
from app.providers.tts.azure import AzureTextToSpeech
from app.telephony.diagnostics import safe_error


async def check_redis(settings: Settings) -> str:
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5)
    try:
        await client.ping()
    finally:
        await client.aclose()
    return "veza radi"


async def check_azure(settings: Settings) -> str:
    audio = await AzureTextToSpeech(settings).synthesize_mulaw("Bok, ovdje Zvonko.")
    return f"govor je generiran ({len(audio)} bajtova); regija={settings.azure_speech_region}"


async def check_deepgram(settings: Settings) -> str:
    if not settings.deepgram_api_key:
        raise ProviderUnavailableError("Deepgram API key is not configured")
    try:
        async with connect(
            STREAM_URL,
            additional_headers={"Authorization": f"Token {settings.deepgram_api_key}"},
            open_timeout=10,
            close_timeout=3,
            max_size=131072,
        ) as connection:
            await connection.send(json.dumps({"type": "CloseStream"}))
    except InvalidStatus as exc:
        raise ProviderUnavailableError(f"Deepgram returned HTTP {exc.response.status_code}") from None
    return "prihvacena veza za nova-3/hr; prepoznavanje govora jos nije testirano"


async def run(settings: Settings) -> bool:
    print("Nema telefonskog poziva. Kratka provjera trosi dio kvote govornih servisa.")
    passed = True
    for name, check in (("Redis", check_redis), ("Azure", check_azure), ("Deepgram", check_deepgram)):
        try:
            async with asyncio.timeout(20):
                detail = await check(settings)
            print(f"{name}: OK - {detail}")
        except Exception as exc:
            passed = False
            print(f"{name}: FAIL - {json.dumps(safe_error(exc))}")
    return passed


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(run(get_settings())) else 1)
