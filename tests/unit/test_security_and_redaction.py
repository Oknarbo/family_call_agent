"""Provider validation and privacy tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.telephony.infobip_client import InfobipVoiceClient
from app.telephony.media_stream import MediaStreamSession
from app.utils.redaction import redact_mapping, redact_phone


def test_sensitive_logs_are_redacted() -> None:
    result = redact_mapping(
        {"phone": "+385 91 123 4567", "authorization": "Bearer secret", "nested": {"api_key": "key"}}
    )
    assert result["authorization"] == "[REDACTED]"
    assert result["nested"] == {"api_key": "[REDACTED]"}
    assert "+385" not in str(result["phone"])
    assert "67" in redact_phone("+385 91 123 4567")


def test_duplicate_media_sequence_is_rejected() -> None:
    session = MediaStreamSession("call-123")
    assert session.accept_sequence(1)
    assert not session.accept_sequence(1)


@pytest.mark.asyncio
async def test_infobip_voice_client_sends_tts_payload() -> None:
    settings = Settings(
        infobip_api_key="test-key",
        infobip_from_number="+385910000099",
        infobip_base_url="https://example.infobip.test",
        infobip_tts_language="hr",
    )
    client = InfobipVoiceClient(settings)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "bulkId": "bulk-1",
        "messages": [{"messageId": "msg-1", "status": {"name": "PENDING_ACCEPTED"}}],
    }
    with patch("app.telephony.infobip_client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client
        result = await client.send_voice_message("+385910000001", text="Popij tabletu.")
    assert result.message_id == "msg-1"
    assert result.status == "PENDING_ACCEPTED"
    posted = mock_client.post.await_args
    assert posted is not None
    assert posted.kwargs["json"]["language"] == "hr"
    assert posted.kwargs["json"]["text"] == "Popij tabletu."
    assert posted.kwargs["headers"]["Authorization"] == "App test-key"


@pytest.mark.asyncio
async def test_infobip_voice_client_supports_audio_url() -> None:
    settings = Settings(
        infobip_api_key="test-key",
        infobip_from_number="385910000099",
        infobip_base_url="https://example.infobip.test",
    )
    client = InfobipVoiceClient(settings)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "messages": [{"messageId": "msg-2", "status": {"name": "PENDING_ACCEPTED"}}],
    }
    with patch("app.telephony.infobip_client.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client
        await client.send_voice_message(
            "385910000001",
            audio_file_url="https://cdn.example.com/reminder.mp3",
        )
    posted = mock_client.post.await_args
    assert posted is not None
    assert posted.kwargs["json"]["audioFileUrl"] == "https://cdn.example.com/reminder.mp3"
    assert "text" not in posted.kwargs["json"]
