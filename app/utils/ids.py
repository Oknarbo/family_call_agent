"""Stable idempotency key generation."""

import hashlib


def idempotency_key(*parts: object) -> str:
    """Hash canonical string parts without exposing sensitive input in logs."""

    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
