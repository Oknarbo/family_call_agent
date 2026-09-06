"""Initial schema frozen independently of runtime models.

SQLAlchemy orders the frozen tables and handles the appointment/call FK cycle.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260804_0001"
down_revision = None
branch_labels = None
depends_on = None


def _schema() -> sa.MetaData:
    metadata = sa.MetaData()
    sa.Table(
        "appointment_reminders",
        metadata,
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reminder_offset_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending_confirmation",
                "scheduled",
                "executing",
                "completed",
                "cancelled",
                "failed",
                name="reminderstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                "remembered",
                "repeat_requested",
                "family_notification_requested",
                "followup_requested",
                "unclear",
                "no_answer",
                name="appointmentreminderoutcome",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("outbound_call_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["appointment_id"],
            ["doctor_appointments.id"],
            name=op.f("fk_appointment_reminders_appointment_id_doctor_appointments"),
        ),
        sa.ForeignKeyConstraint(
            ["outbound_call_id"],
            ["outbound_calls.id"],
            name=op.f("fk_appointment_reminders_outbound_call_id_outbound_calls"),
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["family_members.id"],
            name=op.f("fk_appointment_reminders_target_user_id_family_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointment_reminders")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_appointment_reminders_idempotency_key")),
    )
    sa.Table(
        "family_members",
        metadata,
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("phone_number_e164", sa.String(length=20), nullable=False),
        sa.Column(
            "role", sa.Enum("mama", "tata", "branko", "natasa", name="familyrole", native_enum=False), nullable=False
        ),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notification_preferences", sa.JSON(), nullable=False),
        sa.Column("escalation_preferences", sa.JSON(), nullable=False),
        sa.Column("preferred_assistant_wording", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_family_members")),
    )
    sa.Table(
        "outbound_calls",
        metadata,
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("reminder_id", sa.Uuid(), nullable=True),
        sa.Column("medication_dose_event_id", sa.Uuid(), nullable=True),
        sa.Column("appointment_reminder_id", sa.Uuid(), nullable=True),
        sa.Column("provider_call_id", sa.String(length=128), nullable=True),
        sa.Column(
            "purpose",
            sa.Enum(
                "general_reminder",
                "medication_dose",
                "appointment_reminder",
                "household_safety",
                "family_notification",
                name="outboundcallpurpose",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "scheduled",
                "dialing",
                "ringing",
                "answered",
                "no_answer",
                "busy",
                "failed",
                "completed",
                "cancelled",
                name="outboundcallstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["appointment_reminder_id"],
            ["appointment_reminders.id"],
            name=op.f("fk_outbound_calls_appointment_reminder_id_appointment_reminders"),
        ),
        sa.ForeignKeyConstraint(
            ["medication_dose_event_id"],
            ["medication_dose_events.id"],
            name=op.f("fk_outbound_calls_medication_dose_event_id_medication_dose_events"),
        ),
        sa.ForeignKeyConstraint(
            ["reminder_id"], ["reminders.id"], name=op.f("fk_outbound_calls_reminder_id_reminders")
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["family_members.id"], name=op.f("fk_outbound_calls_target_user_id_family_members")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbound_calls")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_outbound_calls_idempotency_key")),
        sa.UniqueConstraint("provider_call_id", name=op.f("uq_outbound_calls_provider_call_id")),
    )
    sa.Table(
        "audit_events",
        metadata,
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("source_call_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["family_members.id"], name=op.f("fk_audit_events_actor_user_id_family_members")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    sa.Table(
        "call_sessions",
        metadata,
        sa.Column("provider_call_id", sa.String(length=128), nullable=True),
        sa.Column("direction", sa.Enum("inbound", "outbound", name="calldirection", native_enum=False), nullable=False),
        sa.Column("caller_user_id", sa.Uuid(), nullable=True),
        sa.Column("target_user_id", sa.Uuid(), nullable=True),
        sa.Column("caller_phone", sa.String(length=20), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "started", "answered", "no_answer", "busy", "failed", "completed", name="callstatus", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transcript_summary", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["caller_user_id"], ["family_members.id"], name=op.f("fk_call_sessions_caller_user_id_family_members")
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["family_members.id"], name=op.f("fk_call_sessions_target_user_id_family_members")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_sessions")),
        sa.UniqueConstraint("provider_call_id", name=op.f("uq_call_sessions_provider_call_id")),
    )
    sa.Table(
        "doctor_appointments",
        metadata,
        sa.Column("patient_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=160), nullable=True),
        sa.Column("appointment_type", sa.String(length=120), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "scheduled",
                "confirmed",
                "rescheduled",
                "cancelled",
                "completed_user_reported",
                "missed_user_reported",
                "unknown",
                name="appointmentstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("source_call_id", sa.String(length=128), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["family_members.id"],
            name=op.f("fk_doctor_appointments_created_by_user_id_family_members"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_user_id"],
            ["family_members.id"],
            name=op.f("fk_doctor_appointments_patient_user_id_family_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctor_appointments")),
    )
    sa.Table(
        "medication_plans",
        metadata,
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("instructions_label", sa.String(length=255), nullable=True),
        sa.Column("dose_quantity", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("schedule_rule", sa.String(length=255), nullable=False),
        sa.Column("local_schedule_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("current_inventory", sa.Integer(), nullable=True),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("escalation_contact_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["escalation_contact_user_id"],
            ["family_members.id"],
            name=op.f("fk_medication_plans_escalation_contact_user_id_family_members"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["family_members.id"], name=op.f("fk_medication_plans_user_id_family_members")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medication_plans")),
    )
    sa.Table(
        "notifications",
        metadata,
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("related_entity_type", sa.String(length=64), nullable=False),
        sa.Column("related_entity_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_channel", sa.String(length=32), nullable=False),
        sa.Column(
            "delivery_status",
            sa.Enum("pending", "sent", "failed", name="deliverystatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["family_members.id"], name=op.f("fk_notifications_target_user_id_family_members")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    sa.Table(
        "reminders",
        metadata,
        sa.Column("requester_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "reminder_type",
            sa.Enum(
                "general",
                "medication",
                "doctor_appointment",
                "household_safety",
                "family_notification",
                name="remindertype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("reminder_subtype", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("recurrence_rule", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending_confirmation",
                "scheduled",
                "executing",
                "completed",
                "cancelled",
                "failed",
                name="reminderstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("source_call_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("retry_policy", sa.JSON(), nullable=False),
        sa.Column("escalation_policy", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["requester_user_id"], ["family_members.id"], name=op.f("fk_reminders_requester_user_id_family_members")
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"], ["family_members.id"], name=op.f("fk_reminders_target_user_id_family_members")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_reminders_idempotency_key")),
    )
    sa.Table(
        "medication_dose_events",
        metadata,
        sa.Column("medication_plan_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "scheduled",
                "reminder_started",
                "user_reported_taken",
                "user_reported_not_taken",
                "unclear_response",
                "call_later_requested",
                "no_answer",
                "escalated",
                "cancelled",
                name="medicationdosestatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reported_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reported_quantity", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("source_call_id", sa.String(length=128), nullable=True),
        sa.Column("inventory_adjustment_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["medication_plan_id"],
            ["medication_plans.id"],
            name=op.f("fk_medication_dose_events_medication_plan_id_medication_plans"),
        ),
        sa.ForeignKeyConstraint(
            ["reported_by_user_id"],
            ["family_members.id"],
            name=op.f("fk_medication_dose_events_reported_by_user_id_family_members"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["family_members.id"], name=op.f("fk_medication_dose_events_user_id_family_members")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medication_dose_events")),
    )
    sa.Table(
        "medication_inventory_events",
        metadata,
        sa.Column("medication_plan_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "initial_stock",
                "dose_confirmed",
                "box_added",
                "manual_correction",
                "reversal",
                name="medicationinventoryeventtype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("previous_quantity", sa.Integer(), nullable=False),
        sa.Column("new_quantity", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("related_dose_event_id", sa.Uuid(), nullable=True),
        sa.Column("source_call_id", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["family_members.id"],
            name=op.f("fk_medication_inventory_events_actor_user_id_family_members"),
        ),
        sa.ForeignKeyConstraint(
            ["medication_plan_id"],
            ["medication_plans.id"],
            name=op.f("fk_medication_inventory_events_medication_plan_id_medication_plans"),
        ),
        sa.ForeignKeyConstraint(
            ["related_dose_event_id"],
            ["medication_dose_events.id"],
            name=op.f("fk_medication_inventory_events_related_dose_event_id_medication_dose_events"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medication_inventory_events")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_medication_inventory_events_idempotency_key")),
    )
    sa.Index(
        op.f("ix_family_members_phone_number_e164"),
        metadata.tables["family_members"].c["phone_number_e164"],
        unique=True,
    )
    sa.Index(op.f("ix_reminders_scheduled_for"), metadata.tables["reminders"].c["scheduled_for"], unique=False)
    return metadata


def upgrade() -> None:
    _schema().create_all(bind=op.get_bind())


def downgrade() -> None:
    _schema().drop_all(bind=op.get_bind())
