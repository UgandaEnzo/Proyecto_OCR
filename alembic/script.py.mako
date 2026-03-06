"""${message}
Revision ID: ${up_revision}
Revises: ${down_revision | commacomma}
Create Date: ${create_date}
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '${up_revision}'
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade():
${upgrades if upgrades else '    pass'}


def downgrade():
${downgrades if downgrades else '    pass'}
