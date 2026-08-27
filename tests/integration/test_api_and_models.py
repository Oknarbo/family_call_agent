"""Credentials-free FastAPI and SQLAlchemy integration smoke tests."""

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.main import app
from app.models import Base


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "zvonko"}


def test_internal_voice_call_requires_auth() -> None:
    response = TestClient(app).post(
        "/internal/test-voice-call",
        json={"to_number": "+385910000001", "message": "Test"},
    )
    assert response.status_code == 401


async def test_all_models_create_in_sqlite() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    assert len(Base.metadata.tables) == 11
    await engine.dispose()
