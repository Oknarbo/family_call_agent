"""Distributed Redis idempotency lock helper."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


@asynccontextmanager
async def redis_lock(redis: Any, key: str, ttl_seconds: int = 120) -> AsyncIterator[bool]:
    """Acquire a bounded lock; callers skip duplicate work if acquisition fails."""

    lock_key = f"zvonko:lock:{key}"
    acquired = bool(await redis.set(lock_key, "1", ex=ttl_seconds, nx=True))
    try:
        yield acquired
    finally:
        if acquired:
            await redis.delete(lock_key)
