"""add user presence

Revision ID: c3d9f4a1b2e7
Revises: a1f6c7b9e2d3
Create Date: 2026-04-08 02:45:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "c3d9f4a1b2e7"
down_revision = "a1f6c7b9e2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_presence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("sector_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="offline"),
        sa.Column("socket_session_id", sa.String(length=120), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["sector_id"], ["sectors.id"]),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_presence_company_id", "user_presence", ["company_id"], unique=False)
    op.create_index("ix_user_presence_sector_id", "user_presence", ["sector_id"], unique=False)

    op.execute(
        """
        INSERT INTO user_presence (user_id, company_id, sector_id, status, last_heartbeat_at, updated_at)
        SELECT
            id,
            company_id,
            sector_id,
            'offline',
            last_seen,
            COALESCE(last_seen, NOW())
        FROM users
        """
    )

    op.alter_column("user_presence", "status", server_default=None)
    op.alter_column("user_presence", "updated_at", server_default=None)


def downgrade():
    op.drop_index("ix_user_presence_sector_id", table_name="user_presence")
    op.drop_index("ix_user_presence_company_id", table_name="user_presence")
    op.drop_table("user_presence")
