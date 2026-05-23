"""add tasa_momento column to pagos
Revision ID: 20260523_add_tasa_momento_column
Revises: 7f45890161ff
Create Date: 2026-05-23 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260523_add_tasa_momento_column'
down_revision = '7f45890161ff'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pagos', sa.Column('tasa_momento', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('pagos', 'tasa_momento')
