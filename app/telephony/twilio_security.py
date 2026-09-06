"""Twilio form signatures and short-lived media tickets, without trusting proxy headers."""

import base64
import hashlib
import hmac
import json
import re
import time
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from app.config import Settings
from app.domain.exceptions import CallNotPlacedError


def public_origin(settings: Settings) -> str:
    url = urlsplit(settings.public_base_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise CallNotPlacedError("PUBLIC_BASE_URL must be a public HTTPS origin")
    if url.path not in {"", "/"} or url.hostname in {"localhost", "127.0.0.1"}:
        raise CallNotPlacedError("PUBLIC_BASE_URL must have no path")
    return settings.public_base_url.rstrip("/")


def voice_configured(settings: Settings) -> None:
    public_origin(settings)
    if not re.fullmatch(r"AC[0-9a-fA-F]{32}", settings.twilio_account_sid or ""):
        raise CallNotPlacedError("Configure TWILIO_ACCOUNT_SID")
    if not settings.twilio_auth_token or not settings.twilio_from_number:
        raise CallNotPlacedError("Configure Twilio credentials and number")
    if settings.stt_provider != "deepgram" or not settings.deepgram_api_key:
        raise CallNotPlacedError("Configure Deepgram speech recognition")
    if settings.tts_provider != "azure" or not settings.azure_speech_key:
        raise CallNotPlacedError("Configure Azure speech")
    if len(settings.app_secret_key) < 32 or settings.app_secret_key == "development-only-change-me":
        raise CallNotPlacedError("Set a strong APP_SECRET_KEY")


def signature(token: str, url: str, fields: list[tuple[str, str]]) -> str:
    # Twilio sorts field names and distinct values; unknown fields must also be signed.
    payload = url
    for name in sorted({key for key, _ in fields}):
        for value in sorted({value for key, value in fields if key == name}):
            payload += name + value
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


async def verified_form(request: Request, settings: Settings) -> dict[str, str]:
    if not settings.twilio_auth_token or settings.telephony_provider != "twilio":
        raise HTTPException(503, "Twilio is disabled")
    if request.headers.get("content-type", "").split(";")[0] != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Expected a form")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384:
            raise HTTPException(413, "Form too large")
    from urllib.parse import parse_qsl

    try:
        fields = parse_qsl(body.decode("utf-8"), keep_blank_values=True, max_num_fields=100)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid form") from None
    url = public_origin(settings) + request.url.path
    if request.url.query:
        url += "?" + request.url.query
    expected = signature(settings.twilio_auth_token, url, fields)
    if not hmac.compare_digest(expected, request.headers.get("x-twilio-signature", "")):
        raise HTTPException(403, "Invalid signature")
    if len({key for key, _ in fields}) != len(fields):
        raise HTTPException(400, "Repeated fields")
    values = dict(fields)
    if values.get("AccountSid") != settings.twilio_account_sid:
        raise HTTPException(403, "Wrong account")
    if not re.fullmatch(r"CA[0-9a-fA-F]{32}", values.get("CallSid", "")):
        raise HTTPException(400, "Invalid call identifier")
    return values


def media_ticket(settings: Settings, data: dict[str, Any]) -> str:
    payload = dict(data, expires=int(time.time()) + 90)
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    mac = hmac.new(settings.app_secret_key.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + "." + mac


def read_ticket(settings: Settings, value: str) -> dict[str, Any]:
    try:
        encoded, mac = value.split(".", 1)
        expected = hmac.new(settings.app_secret_key.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError
        data: dict[str, Any] = json.loads(base64.urlsafe_b64decode(encoded))
        if data["expires"] < time.time():
            raise ValueError
        return data
    except (ValueError, KeyError, TypeError):
        raise ValueError("Invalid media ticket") from None
