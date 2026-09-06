"""Shared deterministic service fixtures."""

from collections.abc import Iterator

import pytest

from app.config import Settings, get_settings
from app.dependencies import development_store
from app.repositories.memory import MemoryStore
from app.schemas import FamilyMemberRecord
from app.services.family_directory import FamilyDirectory


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Never load personal dotenv files or inherited provider credentials in tests."""
    import os

    fields = {name.casefold() for name in Settings.model_fields}
    for name in list(os.environ):
        if name.casefold() in fields:
            monkeypatch.delenv(name)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    development_store.cache_clear()
    yield
    get_settings.cache_clear()
    development_store.cache_clear()


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
