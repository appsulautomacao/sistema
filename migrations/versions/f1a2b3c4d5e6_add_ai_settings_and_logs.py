"""add ai settings and log fields

Revision ID: f1a2b3c4d5e6
Revises: e7c1a2b3c4d5
Create Date: 2026-04-19 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e7c1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("company_settings", sa.Column("ai_classifier_model", sa.String(length=120), nullable=True))
    op.add_column("company_settings", sa.Column("ai_classifier_prompt", sa.Text(), nullable=True))
    op.execute("UPDATE company_settings SET ai_classifier_model = 'gpt-4o-mini' WHERE ai_classifier_model IS NULL")
    op.alter_column("company_settings", "ai_classifier_model", existing_type=sa.String(length=120), nullable=False)

    op.add_column("ai_logs", sa.Column("company_id", sa.Integer(), nullable=True))
    op.add_column("ai_logs", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column("ai_logs", sa.Column("model_name", sa.String(length=120), nullable=True))
    op.add_column("ai_logs", sa.Column("used_fallback", sa.Boolean(), nullable=True))
    op.add_column("ai_logs", sa.Column("raw_output", sa.Text(), nullable=True))
    op.add_column("ai_logs", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.execute("UPDATE ai_logs SET used_fallback = false WHERE used_fallback IS NULL")
    op.alter_column("ai_logs", "used_fallback", existing_type=sa.Boolean(), nullable=False)

    op.create_index("ix_ai_logs_company_id", "ai_logs", ["company_id"], unique=False)
    op.create_foreign_key(
        "fk_ai_logs_company_id_companies",
        "ai_logs",
        "companies",
        ["company_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_ai_logs_company_id_companies", "ai_logs", type_="foreignkey")
    op.drop_index("ix_ai_logs_company_id", table_name="ai_logs")
    op.drop_column("ai_logs", "failure_reason")
    op.drop_column("ai_logs", "raw_output")
    op.drop_column("ai_logs", "used_fallback")
    op.drop_column("ai_logs", "model_name")
    op.drop_column("ai_logs", "provider")
    op.drop_column("ai_logs", "company_id")
    op.drop_column("company_settings", "ai_classifier_prompt")
    op.drop_column("company_settings", "ai_classifier_model")
