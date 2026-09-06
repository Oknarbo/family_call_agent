"""Bounded daily/weekly occurrence generation in the family's local timezone."""

from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.exceptions import ValidationError

DAY_CODES = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def occurrences(
    rule: str, clock: time, timezone: str, *, start: datetime, end: datetime, clock_override: bool = False
) -> Iterator[datetime]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Occurrence bounds must be timezone-aware")
    try:
        parts = dict(item.split("=", 1) for item in rule.split(";"))
        if parts.get("FREQ") not in {"DAILY", "WEEKLY"} or set(parts) - {"FREQ", "BYHOUR", "BYMINUTE", "BYDAY"}:
            raise ValueError("Unsupported recurrence rule")
        hour, minute = int(parts.get("BYHOUR", clock.hour)), int(parts.get("BYMINUTE", clock.minute))
        local_clock = time(hour, minute)
        if clock_override:
            # Medication plans have a separate editable local time field.
            local_clock = clock
        weekday = None
        if parts["FREQ"] == "WEEKLY":
            value = parts["BYDAY"]
            weekday = DAY_CODES[value] if value in DAY_CODES else int(value)
            if weekday not in range(7):
                raise ValueError("Invalid weekday")
        elif "BYDAY" in parts:
            raise ValueError("BYDAY requires WEEKLY")
        zone = ZoneInfo(timezone)
    except (ValueError, KeyError) as exc:
        raise ValidationError("Unsupported recurrence") from exc
    day = start.astimezone(zone).date()
    last = end.astimezone(zone).date()
    while day <= last:
        if weekday is None or day.weekday() == weekday:
            # fold=0 emits one occurrence on autumn rollback. A spring gap is
            # moved forward by the UTC round trip (02:30 -> 03:30 in Zagreb).
            candidate = datetime.combine(day, local_clock, zone).astimezone(UTC)
            if start <= candidate <= end:
                yield candidate
        day += timedelta(days=1)
