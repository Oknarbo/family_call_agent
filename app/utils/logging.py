"""Structured logging setup."""

import logging

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure JSON logs suitable for containers."""

    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ]
    )
