"""add banco_emisor column to pagos
Revision ID: 20260404_add_banco_emisor_column
Revises: 335b7bb5055d
Create Date: 2026-04-04 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260404_add_banco_emisor_column'
down_revision = '335b7bb5055d'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pagos', sa.Column('banco_emisor', sa.String(), nullable=True))


def downgrade():
    op.drop_column('pagos', 'banco_emisor')
