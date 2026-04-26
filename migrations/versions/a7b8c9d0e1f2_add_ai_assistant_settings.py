"""add ai assistant settings

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-04-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("company_settings", sa.Column("ai_assistant_model", sa.String(length=120), nullable=True))
    op.add_column("company_settings", sa.Column("ai_assistant_prompt", sa.Text(), nullable=True))
    op.execute("UPDATE company_settings SET ai_assistant_model = 'gpt-4o-mini' WHERE ai_assistant_model IS NULL")
    op.alter_column("company_settings", "ai_assistant_model", existing_type=sa.String(length=120), nullable=False)


def downgrade():
    op.drop_column("company_settings", "ai_assistant_prompt")
    op.drop_column("company_settings", "ai_assistant_model")
