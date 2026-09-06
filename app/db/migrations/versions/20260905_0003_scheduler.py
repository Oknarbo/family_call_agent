"""Durable occurrence, dispatch and response metadata."""

from alembic import op
import sqlalchemy as sa

revision = "20260905_0003"
down_revision = "20260905_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("outbound_calls") as batch:
        # The enum uses VARCHAR, without a database CHECK constraint.
        batch.alter_column("status", existing_type=sa.String(9), type_=sa.String(16), existing_nullable=False)
        batch.alter_column(
            "idempotency_key", existing_type=sa.String(128), type_=sa.String(255), existing_nullable=False
        )
        batch.add_column(sa.Column("occurrence_for", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("source_version", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("error_code", sa.String(64), nullable=True))
        batch.add_column(sa.Column("user_outcome", sa.String(64), nullable=True))
        batch.create_index("ix_outbound_calls_status_scheduled_for", ["status", "scheduled_for"])


def downgrade() -> None:
    op.execute("UPDATE outbound_calls SET status='failed' WHERE status='delivery_unknown'")
    with op.batch_alter_table("outbound_calls") as batch:
        batch.drop_index("ix_outbound_calls_status_scheduled_for")
        for name in ("user_outcome", "error_code", "priority", "source_version", "occurrence_for"):
            batch.drop_column(name)
        batch.alter_column("status", existing_type=sa.String(16), type_=sa.String(9), existing_nullable=False)
        # Keep the widened key column: existing long occurrence keys must survive.
