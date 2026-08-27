"""Small deterministic recurrence helpers."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS_HR = {
    "ponedjeljak": 0,
    "utorak": 1,
    "srijeda": 2,
    "četvrtak": 3,
    "petak": 4,
    "subota": 5,
    "nedjelja": 6,
}


def next_daily_occurrence(local_time: time, timezone: str, now: datetime) -> datetime:
    """Return the next daily occurrence in UTC, respecting DST."""

    zone = ZoneInfo(timezone)
    local_now = now.astimezone(zone)
    candidate = datetime.combine(local_now.date(), local_time, zone)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


def next_weekday_occurrence(weekday: int, local_time: time, timezone: str, now: datetime) -> datetime:
    """Return the next named weekday in UTC."""

    zone = ZoneInfo(timezone)
    local_now = now.astimezone(zone)
    days = (weekday - local_now.weekday()) % 7
    candidate = datetime.combine(local_now.date() + timedelta(days=days), local_time, zone)
    if candidate <= local_now:
        candidate += timedelta(days=7)
    return candidate.astimezone(UTC)
