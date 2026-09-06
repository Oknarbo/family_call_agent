"""Twilio protocol contracts without calling any real number."""

import time
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.domain.exceptions import CallNotPlacedError, ProviderUnavailableError
from app.providers.stt.deepgram import FinalUtterances
from app.providers.telephony.twilio import TwilioTelephonyProvider
from app.services.voice_conversation import response_outcome, snooze_minutes
from app.telephony.twilio_security import media_ticket, read_ticket, signature


def configured(**kwargs: object) -> Settings:
    return Settings(
        **dict(
            {
                "telephony_provider": "twilio",
                "stt_provider": "deepgram",
                "tts_provider": "azure",
                "twilio_account_sid": "AC" + "1" * 32,
                "twilio_auth_token": "fake-token",
                "twilio_from_number": "+12025550123",
                "deepgram_api_key": "fake-dg",
                "azure_speech_key": "fake-azure",
                "app_secret_key": "s" * 64,
                "public_base_url": "https://voice.example.test",
            },
            **kwargs,
        )
    )


async def test_twilio_submission_has_callbacks_and_no_recording() -> None:
    reference = str(uuid4())

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.twilio.com"
        data = parse_qs(request.content.decode())
        assert data["Url"] == [f"https://voice.example.test/twilio/outbound/{reference}"]
        assert data["StatusCallback"] == [f"https://voice.example.test/twilio/status/{reference}"]
        assert data["StatusCallbackEvent"] == ["initiated", "ringing", "answered", "completed"]
        assert data["Timeout"] == ["30"]
        assert "Record" not in data and "Twiml" not in data
        assert "private reminder" not in request.content.decode()
        return httpx.Response(201, json={"sid": "CA" + "2" * 32, "status": "queued"})

    provider = TwilioTelephonyProvider(configured(), transport=httpx.MockTransport(handle))
    placed = await provider.place_call("+385910000003", "private reminder", client_reference=reference)
    assert placed.provider_call_id == "CA" + "2" * 32


async def test_separate_verified_outbound_identity() -> None:
    settings = configured(twilio_outbound_caller_id="+385910000004")

    def handle(request: httpx.Request) -> httpx.Response:
        assert parse_qs(request.content.decode())["From"] == ["+385910000004"]
        return httpx.Response(201, json={"sid": "CA" + "2" * 32})

    await TwilioTelephonyProvider(settings, transport=httpx.MockTransport(handle)).place_call(
        "+385910000003", "test", client_reference=str(uuid4())
    )
    assert settings.twilio_from_number != settings.outbound_caller_id
    assert configured(twilio_outbound_caller_id="").outbound_caller_id == settings.twilio_from_number


@pytest.mark.parametrize(
    "code,known", [(400, True), (401, True), (429, True), (408, False), (500, False), (302, False)]
)
async def test_twilio_errors_never_retry_or_leak(code: int, known: bool) -> None:
    count = 0

    def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(code, text="private-token", headers={"Location": "https://elsewhere.test"})

    provider = TwilioTelephonyProvider(configured(), transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderUnavailableError) as error:
        await provider.place_call("+385910000003", "test", client_reference=str(uuid4()))
    assert isinstance(error.value, CallNotPlacedError) == known
    assert "private-token" not in str(error.value)
    assert count == 1


async def test_twilio_timeout_is_unknown_and_missing_config_never_sends() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret")

    provider = TwilioTelephonyProvider(configured(), transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderUnavailableError) as error:
        await provider.place_call("+385910000003", "test", client_reference=str(uuid4()))
    assert not isinstance(error.value, CallNotPlacedError)
    with pytest.raises(CallNotPlacedError):
        await TwilioTelephonyProvider(configured(azure_speech_key=None)).place_call("+385910000003", "test")


def test_signature_uses_query_all_fields_and_sorted_values() -> None:
    fields = [("To", "+385"), ("From", "+1217"), ("FutureField", "čaj")]
    value = signature("token", "https://voice.test/hook?id=1", fields)
    assert value == signature("token", "https://voice.test/hook?id=1", list(reversed(fields)))
    assert value != signature("token", "https://voice.test/hook?id=2", fields)
    assert value != signature("token", "https://voice.test/hook?id=1", fields[:-1])


def test_signature_matches_twilio_official_reference_vector() -> None:
    # https://github.com/twilio/twilio-python/blob/main/tests/unit/test_request_validator.py
    fields = {
        "CallSid": "CA1234567890ABCDE",
        "Digits": "1234",
        "From": "+14158675309",
        "To": "+18005551212",
        "Caller": "+14158675309",
    }
    assert (
        signature("12345", "https://mycompany.com/myapp.php?foo=1&bar=2", list(fields.items()))
        == "RSOYDt4T1cUTdK1PDd93/VVr8B8="
    )


def test_tickets_reject_tampering_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = configured()
    now = time.time()
    ticket = media_ticket(settings, {"sid": "CA123"})
    assert read_ticket(settings, ticket)["sid"] == "CA123"
    with pytest.raises(ValueError):
        read_ticket(settings, ticket + "x")
    monkeypatch.setattr(time, "time", lambda: now + 100)
    with pytest.raises(ValueError):
        read_ticket(settings, ticket)


@pytest.mark.parametrize(
    "text", ["popila sam možda", "popila sam jučer", "jesam li popila", "ne znam", "nisam sigurna"]
)
def test_uncertain_medication_never_confirms(text: str) -> None:
    assert response_outcome(text, True) == "unclear"


def test_explicit_responses_and_spoken_snooze() -> None:
    assert response_outcome("Popio sam tabletu.", True) == "taken"
    assert response_outcome("Nisam popila tabletu.", True) == "not_taken"
    assert response_outcome("Nisam ugasila plin.", False) == "unclear"
    assert response_outcome("Ugasila sam plin.", False) == "completed"
    assert snooze_minutes("nazovi me za petnaest minuta") == 15
    assert snooze_minutes("nazovi me za dva sata") == 120


def test_final_speech_segments_are_joined_once() -> None:
    final = FinalUtterances()

    def result(start: int, text: str, end: bool) -> dict:
        return {
            "type": "Results",
            "start": start,
            "duration": 1,
            "is_final": True,
            "speech_final": end,
            "channel": {"alternatives": [{"transcript": text, "confidence": 0.99}]},
        }

    assert final.accept(result(0, "podsjeti me", False)) is None
    assert final.accept(result(0, "podsjeti me", False)) is None
    assert final.accept(result(1, "za petnaest minuta", True)) == "podsjeti me za petnaest minuta"
    assert final.accept(result(1, "za petnaest minuta", True)) is None
