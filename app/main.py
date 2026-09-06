"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.internal import router as internal_router
from app.api.twilio_webhooks import router as twilio_router
from app.config import get_settings
from app.utils.logging import configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging(get_settings().log_level)
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="Zvonko", version="0.1.0", lifespan=lifespan)
    application.include_router(health_router)
    application.include_router(internal_router)
    application.include_router(twilio_router)
    return application


app = create_app()
