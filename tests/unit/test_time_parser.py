"""Croatian time and Europe/Zagreb DST tests."""

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.domain.exceptions import SchedulingInPastError, ValidationError
from app.domain.recurrence import next_daily_occurrence
from app.domain.time_parser import parse_appointment_offset, parse_croatian_time

NOW = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("phrase", "minutes"),
    [("za pet minuta", 5), ("za četvrt sata", 15), ("za pola sata", 30), ("za dva sata", 120)],
)
def test_relative_time(phrase: str, minutes: int) -> None:
    parsed = parse_croatian_time(phrase, now=NOW)
    assert (parsed.scheduled_for - NOW).total_seconds() == minutes * 60


def test_half_and_quarter_to() -> None:
    assert parse_croatian_time("u pola deset", now=NOW).local_time == time(9, 30)
    assert parse_croatian_time("u petnaest do devet", now=NOW).local_time == time(8, 45)


def test_recurring_daily_expression() -> None:
    parsed = parse_croatian_time("svaki dan u 12", now=NOW)
    assert parsed.recurrence_rule == "FREQ=DAILY;BYHOUR=12;BYMINUTE=0"


def test_vague_time_requires_clarification() -> None:
    with pytest.raises(ValidationError):
        parse_croatian_time("podsjeti me navečer", now=NOW)


def test_past_time_is_rejected() -> None:
    with pytest.raises(SchedulingInPastError):
        parse_croatian_time("u 7", now=NOW)


def test_dst_spring_transition_preserves_local_clock() -> None:
    before = datetime(2026, 3, 28, 11, 0, tzinfo=UTC)
    occurrence = next_daily_occurrence(time(12, 0), "Europe/Zagreb", before)
    assert occurrence.astimezone(ZoneInfo("Europe/Zagreb")).hour == 12


def test_dst_autumn_transition_preserves_local_clock() -> None:
    before = datetime(2026, 10, 24, 11, 0, tzinfo=UTC)
    occurrence = next_daily_occurrence(time(12, 0), "Europe/Zagreb", before)
    assert occurrence.astimezone(ZoneInfo("Europe/Zagreb")).hour == 12


def test_appointment_offsets() -> None:
    assert parse_appointment_offset("dan prije u 18") == (1440, time(18, 0))
    assert parse_appointment_offset("dva sata prije") == (120, None)
