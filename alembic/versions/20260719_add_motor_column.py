"""add motor column to pagos
Revision ID: 20260719_add_motor_column
Revises: 20260523_add_tasa_momento_column
Create Date: 2026-07-19 00:00:00
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260719_add_motor_column'
down_revision = '20260523_add_tasa_momento_column'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pagos', sa.Column('motor', sa.String(), nullable=True))


def downgrade():
    op.drop_column('pagos', 'motor')
