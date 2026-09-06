"""Persist all service fields and shared idempotency history."""

from alembic import op
import sqlalchemy as sa

revision = "20260905_0002"
down_revision = "20260804_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("doctor_appointments") as batch:
        batch.add_column(sa.Column("reminder_offsets_minutes", sa.JSON(), nullable=False, server_default="[1440,120]"))
        batch.add_column(sa.Column("notify_user_ids", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("idempotency_key", sa.String(255), nullable=True))
        batch.create_unique_constraint("uq_doctor_appointments_idempotency_key", ["idempotency_key"])
    with op.batch_alter_table("outbound_calls") as batch:
        batch.add_column(sa.Column("message", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("related_entity_type", sa.String(64), nullable=False, server_default="legacy"))
        batch.add_column(sa.Column("related_entity_id", sa.Uuid(), nullable=True))
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(255), nullable=True))
        batch.create_unique_constraint("uq_notifications_idempotency_key", ["idempotency_key"])
    op.create_table(
        "idempotency_entries",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
    )
    # Preserve keys that were already present in the initial SQL schema.
    for table in ("reminders", "outbound_calls", "medication_inventory_events"):
        op.execute(
            sa.text(
                f"INSERT INTO idempotency_entries (key, entity_id) SELECT idempotency_key, id FROM {table} "
                "WHERE idempotency_key NOT IN (SELECT key FROM idempotency_entries)"
            )
        )


def downgrade() -> None:
    op.drop_table("idempotency_entries")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_constraint("uq_notifications_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")
    with op.batch_alter_table("outbound_calls") as batch:
        for column in ("related_entity_id", "related_entity_type", "message"):
            batch.drop_column(column)
    with op.batch_alter_table("doctor_appointments") as batch:
        batch.drop_constraint("uq_doctor_appointments_idempotency_key", type_="unique")
        for column in ("idempotency_key", "notify_user_ids", "reminder_offsets_minutes"):
            batch.drop_column(column)
