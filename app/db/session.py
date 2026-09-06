"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings, get_settings


def create_database_engine(settings: Settings) -> AsyncEngine:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def configure_sqlite(connection: Any, _record: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()

    return engine


def create_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Create a session factory without opening a connection eagerly."""

    active = settings or get_settings()
    engine = create_database_engine(active)
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_dependency() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that commits or rolls back once per request."""

    factory = create_session_factory()
    try:
        async with factory() as session, session.begin():
            yield session
    finally:
        await factory.kw["bind"].dispose()
