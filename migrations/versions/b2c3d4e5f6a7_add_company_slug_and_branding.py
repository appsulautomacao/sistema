"""add company slug and branding fields

Revision ID: b2c3d4e5f6a7
Revises: f1a2b3c4d5e6
Create Date: 2026-04-22 00:00:00.000000

"""

import re
import unicodedata

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def _slugify_company_name(value):
    raw = (value or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if not slug:
        slug = "empresa"
    return slug


def upgrade():
    op.add_column("companies", sa.Column("slug", sa.String(length=120), nullable=True))
    op.add_column("companies", sa.Column("primary_color", sa.String(length=7), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, name, slug FROM companies ORDER BY id ASC")).mappings().all()

    used = set()
    for row in rows:
        existing_slug = (row.get("slug") or "").strip()
        base_slug = _slugify_company_name(existing_slug or row.get("name"))
        candidate = base_slug
        suffix = 2
        while candidate in used:
            candidate = f"{base_slug}-{suffix}"
            suffix += 1
        used.add(candidate)

        bind.execute(
            sa.text(
                "UPDATE companies "
                "SET slug = :slug, primary_color = COALESCE(primary_color, '#0D6EFD') "
                "WHERE id = :company_id"
            ),
            {"slug": candidate, "company_id": row["id"]},
        )

    op.alter_column("companies", "slug", existing_type=sa.String(length=120), nullable=False)
    op.alter_column("companies", "primary_color", existing_type=sa.String(length=7), nullable=False)
    op.create_unique_constraint("uq_companies_slug", "companies", ["slug"])
    op.create_index("ix_companies_slug", "companies", ["slug"], unique=False)


def downgrade():
    op.drop_index("ix_companies_slug", table_name="companies")
    op.drop_constraint("uq_companies_slug", "companies", type_="unique")
    op.drop_column("companies", "primary_color")
    op.drop_column("companies", "slug")
