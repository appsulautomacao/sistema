"""add billing events table

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-04-22 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=True),
        sa.Column("payment_status", sa.String(length=80), nullable=True),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("company_name", sa.String(length=120), nullable=True),
        sa.Column("admin_name", sa.String(length=120), nullable=True),
        sa.Column("admin_email", sa.String(length=120), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_events_provider", "billing_events", ["provider"], unique=False)
    op.create_index("ix_billing_events_dedupe_key", "billing_events", ["dedupe_key"], unique=True)
    op.create_index("ix_billing_events_external_event_id", "billing_events", ["external_event_id"], unique=False)
    op.create_index("ix_billing_events_payment_status", "billing_events", ["payment_status"], unique=False)
    op.create_index("ix_billing_events_reference", "billing_events", ["reference"], unique=False)
    op.create_index("ix_billing_events_company_id", "billing_events", ["company_id"], unique=False)
    op.create_index("ix_billing_events_admin_email", "billing_events", ["admin_email"], unique=False)
    op.create_index("ix_billing_events_created_at", "billing_events", ["created_at"], unique=False)


def downgrade():
    op.drop_index("ix_billing_events_created_at", table_name="billing_events")
    op.drop_index("ix_billing_events_admin_email", table_name="billing_events")
    op.drop_index("ix_billing_events_company_id", table_name="billing_events")
    op.drop_index("ix_billing_events_reference", table_name="billing_events")
    op.drop_index("ix_billing_events_payment_status", table_name="billing_events")
    op.drop_index("ix_billing_events_external_event_id", table_name="billing_events")
    op.drop_index("ix_billing_events_dedupe_key", table_name="billing_events")
    op.drop_index("ix_billing_events_provider", table_name="billing_events")
    op.drop_table("billing_events")
