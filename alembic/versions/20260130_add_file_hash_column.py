"""add file_hash column to pagos
Revision ID: 20260130_add_file_hash_column
Revises: 
Create Date: 2026-01-30 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260130_add_file_hash_column'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Añadir columna `file_hash` si no existe
    op.add_column('pagos', sa.Column('file_hash', sa.String(), nullable=True))


def downgrade():
    op.drop_column('pagos', 'file_hash')
