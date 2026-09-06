"""Azure Croatian speech, returning WAV audio or raw Twilio mu-law bytes."""

from typing import Literal
from xml.etree.ElementTree import Element, SubElement, tostring

import httpx

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError


class AzureTextToSpeech:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    async def synthesize(self, text: str, language: str = "hr-HR") -> bytes:
        """16 kHz PCM WAV for playback; no files or transcripts are stored here."""
        return await self._synthesize(text, language, "riff-16khz-16bit-mono-pcm")

    async def synthesize_mulaw(self, text: str) -> bytes:
        """Headerless 8 kHz mu-law for Twilio bidirectional Media Streams."""
        return await self._synthesize(text, "hr-HR", "raw-8khz-8bit-mono-mulaw")

    async def _synthesize(
        self,
        text: str,
        language: str,
        output_format: Literal["riff-16khz-16bit-mono-pcm", "raw-8khz-8bit-mono-mulaw"],
    ) -> bytes:
        if not self.settings.azure_speech_key:
            raise ProviderUnavailableError("Azure Speech key is missing")
        if language != "hr-HR" or not text.strip() or len(text) > 3000:
            raise ProviderUnavailableError("Croatian speech requires 1-3000 characters")
        root = Element(
            "speak", {"version": "1.0", "xmlns": "http://www.w3.org/2001/10/synthesis", "xml:lang": language}
        )
        voice = SubElement(root, "voice", {"name": self.settings.azure_speech_voice})
        SubElement(voice, "prosody", {"rate": f"{self.settings.azure_speech_rate_percent:+d}%"}).text = text
        endpoint = f"https://{self.settings.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1"
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=15, follow_redirects=False) as client:
                response = await client.post(
                    endpoint,
                    content=tostring(root, encoding="utf-8"),
                    headers={
                        "Ocp-Apim-Subscription-Key": self.settings.azure_speech_key,
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": output_format,
                        "User-Agent": "Zvonko",
                    },
                )
        except httpx.HTTPError:
            # Never surface provider bodies, authorization headers or source text.
            raise ProviderUnavailableError("Azure Speech connection failed") from None
        if response.status_code != 200:
            raise ProviderUnavailableError(f"Azure Speech returned HTTP {response.status_code}")
        if not response.content or (
            output_format.startswith("riff") and (response.content[:4] != b"RIFF" or response.content[8:12] != b"WAVE")
        ):
            raise ProviderUnavailableError("Azure Speech returned invalid audio")
        return response.content
