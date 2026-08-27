"""Deterministic parser for common spoken Croatian time expressions."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.exceptions import SchedulingInPastError, ValidationError
from app.domain.recurrence import WEEKDAYS_HR, next_daily_occurrence, next_weekday_occurrence

NUMBER_WORDS = {
    "jedan": 1,
    "jednu": 1,
    "dva": 2,
    "dvije": 2,
    "tri": 3,
    "četiri": 4,
    "pet": 5,
    "šest": 6,
    "sedam": 7,
    "osam": 8,
    "devet": 9,
    "deset": 10,
    "jedanaest": 11,
    "dvanaest": 12,
    "petnaest": 15,
    "dvadeset": 20,
    "trideset": 30,
}
VAGUE_WORDS = {"ujutro", "popodne", "navečer", "poslije ručka", "kasnije"}


@dataclass(frozen=True, slots=True)
class ParsedTime:
    """A UTC scheduled time with an optional recurrence rule."""

    scheduled_for: datetime
    recurrence_rule: str | None = None
    local_time: time | None = None


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().strip().split())


def _number(token: str) -> int:
    if token.isdigit():
        return int(token)
    try:
        return NUMBER_WORDS[token]
    except KeyError as exc:
        raise ValidationError from exc


def _clock(text: str) -> time | None:
    half = re.search(r"u pola\s+(\w+)", text)
    if half:
        hour = _number(half.group(1)) - 1
        return time(hour % 24, 30)
    quarter_to = re.search(r"u (?:petnaest|četvrt) do\s+(\w+)", text)
    if quarter_to:
        hour = _number(quarter_to.group(1)) - 1
        return time(hour % 24, 45)
    noon = re.search(r"(?:u\s+)?podne", text)
    if noon:
        return time(12, 0)
    digital = re.search(r"u\s+(\d{1,2})(?:(?::| i |\.)(\d{1,2}))?", text)
    if digital:
        hour = int(digital.group(1))
        minute = int(digital.group(2) or 0)
        if hour > 23 or minute > 59:
            raise ValidationError
        return time(hour, minute)
    spoken = re.search(
        r"u\s+(jedan|dva|tri|četiri|pet|šest|sedam|osam|devet|deset|jedanaest|dvanaest)",
        text,
    )
    if spoken:
        return time(_number(spoken.group(1)), 0)
    return None


def parse_croatian_time(
    value: str,
    *,
    now: datetime,
    timezone: str = "Europe/Zagreb",
) -> ParsedTime:
    """Parse the supported Croatian relative, weekday and recurring expressions."""

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    text = _normalize(value)
    if any(phrase in text for phrase in VAGUE_WORDS) and _clock(text) is None:
        raise ValidationError("vague time needs clarification")
    zone = ZoneInfo(timezone)
    local_now = now.astimezone(zone)

    if "za četvrt sata" in text:
        return ParsedTime((local_now + timedelta(minutes=15)).astimezone(UTC))
    if "za pola sata" in text:
        return ParsedTime((local_now + timedelta(minutes=30)).astimezone(UTC))
    if "za sat vremena" in text:
        return ParsedTime((local_now + timedelta(hours=1)).astimezone(UTC))
    relative = re.search(r"za\s+(\w+)\s+(minut\w*|sat\w*)", text)
    if relative:
        amount = _number(relative.group(1))
        unit = relative.group(2)
        delta = timedelta(minutes=amount) if unit.startswith("minut") else timedelta(hours=amount)
        return ParsedTime((local_now + delta).astimezone(UTC))

    clock = _clock(text)
    if "svaki dan" in text:
        if clock is None:
            raise ValidationError("missing recurring time")
        return ParsedTime(
            next_daily_occurrence(clock, timezone, now),
            recurrence_rule=f"FREQ=DAILY;BYHOUR={clock.hour};BYMINUTE={clock.minute}",
            local_time=clock,
        )
    for day_name, weekday in WEEKDAYS_HR.items():
        if f"svaki {day_name}" in text:
            if clock is None:
                raise ValidationError("missing recurring time")
            return ParsedTime(
                next_weekday_occurrence(weekday, clock, timezone, now),
                recurrence_rule=(f"FREQ=WEEKLY;BYDAY={weekday};BYHOUR={clock.hour};BYMINUTE={clock.minute}"),
                local_time=clock,
            )

    target_date = local_now.date()
    if "prekosutra" in text:
        target_date += timedelta(days=2)
    elif "sutra" in text:
        target_date += timedelta(days=1)
    else:
        for day_name, weekday in WEEKDAYS_HR.items():
            if day_name in text:
                days = (weekday - local_now.weekday()) % 7
                if days == 0 or f"sljedeći {day_name}" in text:
                    days = 7
                target_date += timedelta(days=days)
                break
    if clock is None:
        raise ValidationError("missing exact time")
    candidate = datetime.combine(target_date, clock, zone)
    if candidate <= local_now and not any(token in text for token in ("sutra", "prekosutra", *WEEKDAYS_HR)):
        raise SchedulingInPastError
    return ParsedTime(candidate.astimezone(UTC), local_time=clock)


def validate_future(value: datetime, *, now: datetime) -> datetime:
    """Reject naive or past timestamps and normalize to UTC."""

    if value.tzinfo is None:
        raise ValidationError("datetime must be aware")
    normalized = value.astimezone(UTC)
    if normalized <= now.astimezone(UTC):
        raise SchedulingInPastError
    return normalized


def parse_appointment_offset(value: str) -> tuple[int, time | None]:
    """Parse supported reminder offsets relative to a doctor appointment."""

    text = _normalize(value)
    if "dan prije" in text:
        return 1440, _clock(text)
    match = re.search(r"(\w+)\s+sata?\s+prije", text)
    if match:
        return _number(match.group(1)) * 60, None
    raise ValidationError("unsupported appointment reminder offset")
