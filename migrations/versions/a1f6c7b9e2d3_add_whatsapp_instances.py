"""add whatsapp instances

Revision ID: a1f6c7b9e2d3
Revises: 9b4b1d9b6f2e
Create Date: 2026-04-08 02:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a1f6c7b9e2d3"
down_revision = "9b4b1d9b6f2e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "whatsapp_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="evolution"),
        sa.Column("instance_name", sa.String(length=120), nullable=False),
        sa.Column("api_key", sa.String(length=255), nullable=True),
        sa.Column("webhook_secret", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="created"),
        sa.Column("last_connection_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.UniqueConstraint("instance_name"),
    )
    op.create_index(
        "ix_whatsapp_instances_company_id",
        "whatsapp_instances",
        ["company_id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO whatsapp_instances (
            company_id,
            provider,
            instance_name,
            api_key,
            status,
            created_at
        )
        SELECT
            id,
            'evolution',
            whatsapp_instance,
            '',
            'created',
            NOW()
        FROM companies
        WHERE whatsapp_instance IS NOT NULL
          AND trim(whatsapp_instance) <> ''
        """
    )

    op.alter_column("whatsapp_instances", "provider", server_default=None)
    op.alter_column("whatsapp_instances", "status", server_default=None)
    op.alter_column("whatsapp_instances", "created_at", server_default=None)


def downgrade():
    op.drop_index("ix_whatsapp_instances_company_id", table_name="whatsapp_instances")
    op.drop_table("whatsapp_instances")
