"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings, get_settings


def create_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Create a session factory without opening a connection eagerly."""

    active = settings or get_settings()
    engine = create_async_engine(active.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_dependency() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that commits or rolls back once per request."""

    factory = create_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
