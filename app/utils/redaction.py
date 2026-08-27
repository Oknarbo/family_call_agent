"""Privacy-preserving log redaction."""

import re
from collections.abc import Mapping
from typing import Any

PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){7,15}(?!\d)")
SENSITIVE_KEYS = {"authorization", "infobip_api_key", "deepgram_api_key", "api_key"}


def redact_phone(value: str) -> str:
    """Keep at most the final two digits of phone-like values."""

    def replacement(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        return f"[PHONE:***{digits[-2:]}]"

    return PHONE_PATTERN.sub(replacement, value)


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively remove credentials and redact phone numbers."""

    result: dict[str, Any] = {}
    for key, value in values.items():
        if key.casefold() in SENSITIVE_KEYS:
            result[key] = "[REDACTED]"
        elif isinstance(value, str):
            result[key] = redact_phone(value)
        elif isinstance(value, Mapping):
            result[key] = redact_mapping(value)
        else:
            result[key] = value
    return result
