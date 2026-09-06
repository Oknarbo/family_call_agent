"""Credentials-free FastAPI and SQLAlchemy integration smoke tests."""

from uuid import uuid4

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
    assert "idempotency_entries" in Base.metadata.tables
    await engine.dispose()


def test_scheduler_operational_endpoints_require_auth() -> None:
    client = TestClient(app)
    assert client.get("/internal/scheduler-status").status_code == 401
    assert (
        client.post(
            "/internal/call-status",
            json={
                "call_id": str(uuid4()),
                "provider_call_id": "fake",
                "status": "no_answer",
            },
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/internal/call-response",
            json={
                "call_id": str(uuid4()),
                "outcome": "taken",
            },
        ).status_code
        == 401
    )
