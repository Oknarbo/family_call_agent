"""Application dependency composition."""

from functools import lru_cache

from app.config import get_settings
from app.repositories.memory import MemoryStore
from app.services.family_directory import FamilyDirectory


@lru_cache
def development_store() -> MemoryStore:
    """Process-local store only for development API smoke tests."""

    store = MemoryStore()
    if not store.family_members:
        FamilyDirectory(store).seed(get_settings())
    return store
