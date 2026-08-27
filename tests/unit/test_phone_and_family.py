"""Caller identification and E.164 tests."""

import pytest

from app.domain.exceptions import InactiveCallerError, UnknownCallerError, ValidationError
from app.repositories.memory import MemoryStore
from app.services.family_directory import FamilyDirectory
from app.utils.phone_numbers import normalize_phone_number


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("091 000 0001", "+385910000001"),
        ("+385 91 000 0002", "+385910000002"),
    ],
)
def test_phone_number_normalization(raw: str, expected: str) -> None:
    assert normalize_phone_number(raw) == expected


def test_malformed_phone_is_rejected() -> None:
    with pytest.raises(ValidationError):
        normalize_phone_number("banana")


def test_registered_caller_is_identified(store: MemoryStore) -> None:
    directory = FamilyDirectory(store)
    assert directory.identify("091 000 0001").display_name == "Mama"


def test_unknown_caller_is_rejected_without_directory_details(store: MemoryStore) -> None:
    with pytest.raises(UnknownCallerError) as captured:
        FamilyDirectory(store).identify("+385991234567")
    assert "Mama" not in captured.value.user_message


def test_inactive_caller_is_rejected(store: MemoryStore) -> None:
    member = FamilyDirectory(store).by_name("tata")
    member.is_active = False
    with pytest.raises(InactiveCallerError):
        FamilyDirectory(store).identify(member.phone_number_e164)
