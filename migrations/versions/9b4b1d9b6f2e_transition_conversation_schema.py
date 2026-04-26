"""transition conversation schema

Revision ID: 9b4b1d9b6f2e
Revises: 1cee7cfbfc64
Create Date: 2026-04-08 01:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9b4b1d9b6f2e"
down_revision = "1cee7cfbfc64"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("sectors", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_central", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("current_sector_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.text("now()"))
        )
        batch_op.add_column(
            sa.Column("last_message_at", sa.DateTime(), nullable=True, server_default=sa.text("now()"))
        )
        batch_op.create_foreign_key(
            "fk_conversations_current_sector_id_sectors",
            "sectors",
            ["current_sector_id"],
            ["id"],
        )

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("company_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sender_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sender_type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("message_type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("external_message_id", sa.String(length=255), nullable=True))
        batch_op.create_index("ix_messages_company_id", ["company_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_messages_company_id_companies",
            "companies",
            ["company_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_messages_sender_user_id_users",
            "users",
            ["sender_user_id"],
            ["id"],
        )

    with op.batch_alter_table("conversation_history", schema=None) as batch_op:
        batch_op.add_column(sa.Column("from_sector_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("to_sector_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("event_type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("metadata_json", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_conversation_history_from_sector_id_sectors",
            "sectors",
            ["from_sector_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_conversation_history_to_sector_id_sectors",
            "sectors",
            ["to_sector_id"],
            ["id"],
        )

    op.execute(
        """
        UPDATE sectors
        SET is_central = CASE
            WHEN lower(trim(name)) = 'central' THEN TRUE
            ELSE FALSE
        END
        """
    )

    op.execute(
        """
        UPDATE conversations
        SET current_sector_id = sector_id
        WHERE current_sector_id IS NULL
        """
    )

    op.execute(
        """
        UPDATE conversations
        SET updated_at = created_at
        WHERE updated_at IS NULL
        """
    )

    op.execute(
        """
        UPDATE conversations
        SET last_message_at = COALESCE(
            (
                SELECT MAX(messages.created_at)
                FROM messages
                WHERE messages.conversation_id = conversations.id
            ),
            created_at
        )
        WHERE last_message_at IS NULL
        """
    )

    op.execute(
        """
        UPDATE messages
        SET sender_type = sender
        WHERE sender_type IS NULL
        """
    )

    op.execute(
        """
        UPDATE messages
        SET message_type = type
        WHERE message_type IS NULL
        """
    )

    op.execute(
        """
        UPDATE messages
        SET company_id = conversations.company_id
        FROM conversations
        WHERE messages.conversation_id = conversations.id
          AND messages.company_id IS NULL
        """
    )

    op.execute(
        """
        UPDATE conversation_history
        SET event_type = action_type
        WHERE event_type IS NULL
        """
    )

    op.execute(
        """
        UPDATE conversation_history
        SET to_sector_id = sector_id
        WHERE to_sector_id IS NULL
        """
    )

    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.alter_column("updated_at", nullable=False, server_default=None)
        batch_op.alter_column("last_message_at", nullable=False, server_default=None)


def downgrade():
    with op.batch_alter_table("conversation_history", schema=None) as batch_op:
        batch_op.drop_constraint("fk_conversation_history_to_sector_id_sectors", type_="foreignkey")
        batch_op.drop_constraint("fk_conversation_history_from_sector_id_sectors", type_="foreignkey")
        batch_op.drop_column("metadata_json")
        batch_op.drop_column("event_type")
        batch_op.drop_column("to_sector_id")
        batch_op.drop_column("from_sector_id")

    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_constraint("fk_messages_sender_user_id_users", type_="foreignkey")
        batch_op.drop_constraint("fk_messages_company_id_companies", type_="foreignkey")
        batch_op.drop_index("ix_messages_company_id")
        batch_op.drop_column("external_message_id")
        batch_op.drop_column("message_type")
        batch_op.drop_column("sender_type")
        batch_op.drop_column("sender_user_id")
        batch_op.drop_column("company_id")

    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.drop_constraint("fk_conversations_current_sector_id_sectors", type_="foreignkey")
        batch_op.drop_column("last_message_at")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("current_sector_id")

    with op.batch_alter_table("sectors", schema=None) as batch_op:
        batch_op.drop_column("is_active")
        batch_op.drop_column("is_central")
