"""Application dependency composition."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings, get_settings
from app.db.session import create_database_engine
from app.repositories.database import DatabaseStore, database_store
from app.repositories.memory import MemoryStore
from app.services.family_directory import FamilyDirectory


@lru_cache
def development_store() -> MemoryStore:
    """Process-local store only for development API smoke tests."""

    store = MemoryStore()
    if not store.family_members:
        FamilyDirectory(store).seed(get_settings())
    return store


@asynccontextmanager
async def application_store(settings: Settings | None = None) -> AsyncIterator[DatabaseStore]:
    """API, conversational turns and worker jobs share DATABASE_URL, not memory."""
    active = settings or get_settings()
    engine = create_database_engine(active)
    try:
        async with database_store(async_sessionmaker(engine, expire_on_commit=False)) as store:
            yield store
    finally:
        await engine.dispose()
