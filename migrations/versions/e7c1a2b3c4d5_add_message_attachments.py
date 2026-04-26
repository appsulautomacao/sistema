"""add message attachments

Revision ID: e7c1a2b3c4d5
Revises: d4e5f6a7b8c9
Create Date: 2026-04-13 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "e7c1a2b3c4d5"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("provider_media_url", sa.Text(), nullable=True),
        sa.Column("storage_backend", sa.String(length=30), nullable=False, server_default="local"),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("safe_filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("extension", sa.String(length=32), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("attachment_type", sa.String(length=50), nullable=False, server_default="document"),
        sa.Column("download_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("download_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("download_error", sa.Text(), nullable=True),
        sa.Column("is_inbound", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("downloaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], name="fk_message_attachments_message_id_messages"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], name="fk_message_attachments_conversation_id_conversations"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_message_attachments_company_id_companies"),
        sa.ForeignKeyConstraint(["downloaded_by_user_id"], ["users.id"], name="fk_message_attachments_downloaded_by_user_id_users"),
    )
    op.create_index("ix_message_attachments_message_id", "message_attachments", ["message_id"], unique=False)
    op.create_index("ix_message_attachments_conversation_id", "message_attachments", ["conversation_id"], unique=False)
    op.create_index("ix_message_attachments_company_id", "message_attachments", ["company_id"], unique=False)
    op.create_index("ix_message_attachments_provider_message_id", "message_attachments", ["provider_message_id"], unique=False)
    op.create_index("ix_message_attachments_created_at", "message_attachments", ["created_at"], unique=False)


def downgrade():
    op.drop_index("ix_message_attachments_created_at", table_name="message_attachments")
    op.drop_index("ix_message_attachments_provider_message_id", table_name="message_attachments")
    op.drop_index("ix_message_attachments_company_id", table_name="message_attachments")
    op.drop_index("ix_message_attachments_conversation_id", table_name="message_attachments")
    op.drop_index("ix_message_attachments_message_id", table_name="message_attachments")
    op.drop_table("message_attachments")
