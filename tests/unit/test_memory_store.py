"""Development persistence behavior."""

from pathlib import Path

from app.config import Settings
from app.repositories.memory import MemoryStore
from app.services.family_directory import FamilyDirectory


def test_json_store_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = MemoryStore(path)
    FamilyDirectory(store).seed(Settings(app_env="test"))
    loaded = MemoryStore(path)
    assert len(loaded.family_members) == 4
    assert FamilyDirectory(loaded).by_name("Nataša").display_name == "Nataša"


def test_reset_removes_development_data(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    store = MemoryStore(path)
    FamilyDirectory(store).seed(Settings(app_env="test"))
    store.reset()
    assert store.family_members == {}
