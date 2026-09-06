"""Provider contract and local setup without live credentials or paid requests."""

from pathlib import Path
from xml.etree import ElementTree

import httpx
import pytest
from dotenv import dotenv_values

from app.config import Settings
from app.domain.exceptions import ProviderUnavailableError
from app.providers.tts.azure import AzureTextToSpeech
from app.providers.tts.factory import create_tts_provider
from scripts.setup_azure import save_configuration


@pytest.mark.parametrize("mulaw", [False, True])
async def test_azure_audio_format_and_escaped_croatian(mulaw: bool) -> None:
    audio = b"\xff\xfe" if mulaw else b"RIFF\x04\x00\x00\x00WAVE"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "westeurope.tts.speech.microsoft.com"
        assert request.headers["Ocp-Apim-Subscription-Key"] == "test-key"
        root = ElementTree.fromstring(request.content)
        ns = {"s": "http://www.w3.org/2001/10/synthesis"}
        voice = root.find("s:voice", ns)
        assert voice is not None and voice.attrib["name"] == "hr-HR-SreckoNeural"
        prosody = root.find("s:voice/s:prosody", ns)
        assert prosody is not None and prosody.text == "Čaj & <plin>"
        assert prosody.attrib["rate"] == "-10%"
        assert request.headers["X-Microsoft-OutputFormat"] == (
            "raw-8khz-8bit-mono-mulaw" if mulaw else "riff-16khz-16bit-mono-pcm"
        )
        return httpx.Response(200, content=audio)

    provider = AzureTextToSpeech(Settings(azure_speech_key="test-key"), transport=httpx.MockTransport(handler))
    result = await provider.synthesize_mulaw("Čaj & <plin>") if mulaw else await provider.synthesize("Čaj & <plin>")
    assert result == audio


@pytest.mark.parametrize("code", [301, 401, 403, 429, 500])
async def test_provider_failure_does_not_leak_secrets_or_retry(code: int) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            code, text="private-key private-medication", headers={"Location": "https://elsewhere.test"}
        )

    provider = AzureTextToSpeech(Settings(azure_speech_key="private-key"), transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderUnavailableError) as error:
        await provider.synthesize("private-medication")
    assert "private" not in str(error.value)
    assert str(code) in str(error.value)
    assert calls == 1


async def test_missing_key_does_not_call_provider() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        pytest.fail("Must not make a request without credentials")

    with pytest.raises(ProviderUnavailableError):
        await AzureTextToSpeech(Settings(), transport=httpx.MockTransport(handler)).synthesize("Bok")
    assert isinstance(create_tts_provider(Settings(tts_provider="azure")), AzureTextToSpeech)


@pytest.mark.parametrize("content", [b"", b"not-a-wave-file"])
async def test_rejects_invalid_audio(content: bytes) -> None:
    provider = AzureTextToSpeech(
        Settings(azure_speech_key="test-key"),
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=content)),
    )
    with pytest.raises(ProviderUnavailableError):
        await provider.synthesize("Bok")


async def test_network_failure_is_sanitized() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret text")

    provider = AzureTextToSpeech(Settings(azure_speech_key="test-key"), transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderUnavailableError) as error:
        await provider.synthesize("Bok")
    assert "secret" not in str(error.value)


def test_setup_preserves_other_settings_and_replaces_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# Keep me\nAPP_SECRET_KEY=other-secret\nAZURE_SPEECH_KEY=old\nexport AZURE_SPEECH_KEY=older\n",
        encoding="utf-8",
    )
    save_configuration(path, "a" * 32, "westeurope")
    result = dotenv_values(path)
    assert result["APP_SECRET_KEY"] == "other-secret"
    assert result["AZURE_SPEECH_KEY"] == "a" * 32
    assert result["TTS_PROVIDER"] == "azure"
    assert path.read_text().count("AZURE_SPEECH_KEY=") == 1
    before = path.read_bytes()
    with pytest.raises(ValueError):
        save_configuration(path, "invalid\ninjection", "westeurope")
    assert path.read_bytes() == before
