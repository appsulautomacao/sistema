"""add conversation routings

Revision ID: d4e5f6a7b8c9
Revises: c3d9f4a1b2e7
Create Date: 2026-04-08 03:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "c3d9f4a1b2e7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversation_routings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("sector_id", sa.Integer(), nullable=False),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        sa.Column("transferred_by", sa.Integer(), nullable=True),
        sa.Column("transfer_reason", sa.String(length=255), nullable=True),
        sa.Column("entered_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("left_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["sector_id"], ["sectors.id"]),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"]),
        sa.ForeignKeyConstraint(["transferred_by"], ["users.id"]),
    )
    op.create_index("ix_conversation_routings_conversation_id", "conversation_routings", ["conversation_id"], unique=False)
    op.create_index("ix_conversation_routings_company_id", "conversation_routings", ["company_id"], unique=False)
    op.create_index("ix_conversation_routings_sector_id", "conversation_routings", ["sector_id"], unique=False)

    op.execute(
        """
        INSERT INTO conversation_routings (
            conversation_id,
            company_id,
            sector_id,
            assigned_to,
            entered_at,
            left_at
        )
        SELECT
            c.id,
            c.company_id,
            c.current_sector_id,
            c.assigned_to,
            c.created_at,
            CASE
                WHEN c.current_sector_id IS NULL THEN c.updated_at
                ELSE NULL
            END
        FROM conversations c
        WHERE c.current_sector_id IS NOT NULL
        """
    )

    op.alter_column("conversation_routings", "entered_at", server_default=None)


def downgrade():
    op.drop_index("ix_conversation_routings_sector_id", table_name="conversation_routings")
    op.drop_index("ix_conversation_routings_company_id", table_name="conversation_routings")
    op.drop_index("ix_conversation_routings_conversation_id", table_name="conversation_routings")
    op.drop_table("conversation_routings")
