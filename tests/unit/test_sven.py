"""Optional family registration preserves existing members and escalation order."""

import pytest

from app.config import Settings
from app.domain.exceptions import ValidationError
from app.repositories.memory import MemoryStore
from app.services.family_directory import FamilyDirectory


def test_sven_is_optional_and_seed_preserves_existing_members(store: MemoryStore) -> None:
    directory = FamilyDirectory(store)
    mama = directory.by_name("Mama")
    original = mama.model_dump()
    assert len(store.family_members) == 4
    settings = Settings(sven_phone_e164="+385910000005", mama_phone_e164="+385910000009")
    assert len(directory.seed(settings)) == 1
    sven = directory.identify("+385910000005")
    assert directory.by_name("Svenu").id == sven.id
    assert mama.model_dump() == original
    assert directory.seed(settings) == []
    assert sven.escalation_preferences["important_no_answer_contact_ids"] == [
        str(directory.by_name("Branko").id),
        str(directory.by_name("Nataša").id),
    ]


def test_duplicate_sven_phone_is_rejected_without_partial_changes(store: MemoryStore) -> None:
    directory = FamilyDirectory(store)
    with pytest.raises(ValidationError):
        directory.seed(Settings(sven_phone_e164=directory.by_name("Mama").phone_number_e164))
    assert len(store.family_members) == 4
