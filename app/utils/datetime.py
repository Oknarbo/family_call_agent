"""Timezone-safe datetime helpers."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


def require_aware(value: datetime) -> datetime:
    """Reject naive datetimes."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


def to_utc(value: datetime) -> datetime:
    """Normalize an aware value to UTC."""

    return require_aware(value).astimezone(UTC)


def to_local(value: datetime, timezone: str = "Europe/Zagreb") -> datetime:
    """Render a stored UTC timestamp in a family member's local timezone."""

    return require_aware(value).astimezone(ZoneInfo(timezone))
