"""Initial Zvonko schema.

Revision ID: 20260804_0001
Revises:
"""

from collections.abc import Sequence

from alembic import op

from app.models import Base

revision: str = "20260804_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the full initial modular-monolith schema."""

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Drop all Zvonko tables for an explicit development rollback."""

    Base.metadata.drop_all(bind=op.get_bind())

