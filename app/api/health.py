"""Health endpoints that avoid leaking configuration."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "zvonko"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}
