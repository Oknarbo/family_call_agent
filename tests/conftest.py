"""Shared deterministic service fixtures."""

from collections.abc import Iterator

import pytest

from app.config import Settings
from app.repositories.memory import MemoryStore
from app.schemas import FamilyMemberRecord
from app.services.family_directory import FamilyDirectory


@pytest.fixture
def settings() -> Settings:
    return Settings(app_env="test", database_url="sqlite+aiosqlite:///:memory:")


@pytest.fixture
def store(settings: Settings) -> MemoryStore:
    value = MemoryStore()
    FamilyDirectory(value).seed(settings)
    return value


@pytest.fixture
def mama(store: MemoryStore) -> FamilyMemberRecord:
    return FamilyDirectory(store).by_name("mama")


@pytest.fixture
def branko(store: MemoryStore) -> FamilyMemberRecord:
    return FamilyDirectory(store).by_name("branko")


@pytest.fixture
def seeded(store: MemoryStore) -> Iterator[MemoryStore]:
    yield store
