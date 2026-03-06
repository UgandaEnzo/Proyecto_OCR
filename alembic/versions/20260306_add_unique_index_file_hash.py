"""add unique index on pagos.file_hash

Revision ID: 20260306_add_unique_index_file_hash
Revises: 20260130_add_file_hash_column
Create Date: 2026-03-06

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260306_add_unique_index_file_hash"
down_revision = "20260130_add_file_hash_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL: UNIQUE permite múltiples NULL, así que sirve para deduplicado por hash.
    op.create_index(
        "uq_pagos_file_hash",
        "pagos",
        ["file_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_pagos_file_hash", table_name="pagos")
