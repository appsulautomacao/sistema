"""add commercial billing foundation

Revision ID: d9f0a1b2c3d4
Revises: c4d5e6f7a8b9
Create Date: 2026-04-23 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d9f0a1b2c3d4"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_tables = set(inspector.get_table_names())

    if "billing_plans" not in existing_tables:
        op.create_table(
            "billing_plans",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("billing_period", sa.String(length=40), nullable=False),
            sa.Column("billing_cycle_months", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("price_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="BRL"),
            sa.Column("setup_fee_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_installments", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("allow_pix", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("allow_boleto", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("allow_card", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("highlight_text", sa.String(length=120), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_billing_plans_code"),
        )

    if "checkout_sessions" not in existing_tables:
        op.create_table(
            "checkout_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("public_token", sa.String(length=64), nullable=False),
            sa.Column("plan_id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=True),
            sa.Column("company_name", sa.String(length=120), nullable=False),
            sa.Column("admin_name", sa.String(length=120), nullable=False),
            sa.Column("admin_email", sa.String(length=120), nullable=False),
            sa.Column("customer_document", sa.String(length=50), nullable=True),
            sa.Column("payment_method", sa.String(length=40), nullable=False, server_default="card"),
            sa.Column("installment_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="BRL"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="created"),
            sa.Column("provider", sa.String(length=50), nullable=False, server_default="pagseguro"),
            sa.Column("external_checkout_id", sa.String(length=255), nullable=True),
            sa.Column("success_url", sa.String(length=500), nullable=True),
            sa.Column("cancel_url", sa.String(length=500), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("paid_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["plan_id"], ["billing_plans.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_token", name="uq_checkout_sessions_public_token"),
        )

    if "subscriptions" not in existing_tables:
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("plan_id", sa.Integer(), nullable=False),
            sa.Column("checkout_session_id", sa.Integer(), nullable=True),
            sa.Column("provider", sa.String(length=50), nullable=False, server_default="pagseguro"),
            sa.Column("external_subscription_id", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("billing_period", sa.String(length=40), nullable=False, server_default="monthly"),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="BRL"),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("current_period_start", sa.DateTime(), nullable=True),
            sa.Column("current_period_end", sa.DateTime(), nullable=True),
            sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("canceled_at", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["checkout_session_id"], ["checkout_sessions.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["plan_id"], ["billing_plans.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "payment_transactions" not in existing_tables:
        op.create_table(
            "payment_transactions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=True),
            sa.Column("subscription_id", sa.Integer(), nullable=True),
            sa.Column("checkout_session_id", sa.Integer(), nullable=True),
            sa.Column("billing_event_id", sa.Integer(), nullable=True),
            sa.Column("provider", sa.String(length=50), nullable=False, server_default="pagseguro"),
            sa.Column("external_payment_id", sa.String(length=255), nullable=True),
            sa.Column("payment_method", sa.String(length=40), nullable=True),
            sa.Column("installment_count", sa.Integer(), nullable=True),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="BRL"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("paid_at", sa.DateTime(), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["billing_event_id"], ["billing_events.id"]),
            sa.ForeignKeyConstraint(["checkout_session_id"], ["checkout_sessions.id"]),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_columns = {column["name"] for column in inspector.get_columns("billing_events")}
    if "checkout_session_id" not in existing_columns:
        op.add_column("billing_events", sa.Column("checkout_session_id", sa.Integer(), nullable=True))
    if "plan_code" not in existing_columns:
        op.add_column("billing_events", sa.Column("plan_code", sa.String(length=80), nullable=True))
    if "billing_period" not in existing_columns:
        op.add_column("billing_events", sa.Column("billing_period", sa.String(length=40), nullable=True))
    if "payment_method" not in existing_columns:
        op.add_column("billing_events", sa.Column("payment_method", sa.String(length=40), nullable=True))
    if "installment_count" not in existing_columns:
        op.add_column("billing_events", sa.Column("installment_count", sa.Integer(), nullable=True))
    if "amount_cents" not in existing_columns:
        op.add_column("billing_events", sa.Column("amount_cents", sa.Integer(), nullable=True))


def downgrade():
    op.drop_index("ix_billing_events_plan_code", table_name="billing_events")
    op.drop_index("ix_billing_events_checkout_session_id", table_name="billing_events")
    op.drop_constraint("fk_billing_events_checkout_session_id", "billing_events", type_="foreignkey")
    op.drop_column("billing_events", "amount_cents")
    op.drop_column("billing_events", "installment_count")
    op.drop_column("billing_events", "payment_method")
    op.drop_column("billing_events", "billing_period")
    op.drop_column("billing_events", "plan_code")
    op.drop_column("billing_events", "checkout_session_id")

    op.drop_index("ix_payment_transactions_status", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_external_payment_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_billing_event_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_checkout_session_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_subscription_id", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_company_id", table_name="payment_transactions")
    op.drop_table("payment_transactions")

    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_external_subscription_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_checkout_session_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_plan_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_company_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("ix_checkout_sessions_created_at", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_external_checkout_id", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_status", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_admin_email", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_company_id", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_plan_id", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_public_token", table_name="checkout_sessions")
    op.drop_table("checkout_sessions")

    op.drop_index("ix_billing_plans_billing_period", table_name="billing_plans")
    op.drop_index("ix_billing_plans_code", table_name="billing_plans")
    op.drop_table("billing_plans")
