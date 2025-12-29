"""add job control fields

Revision ID: 20251229195900
Revises: 20251229160000
Create Date: 2025-12-29 19:59:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251229195900'
down_revision = '20251229160000'
branch_labels = None
depends_on = None


def upgrade():
    # Add pause_requested column
    op.add_column('jobs', sa.Column('pause_requested', sa.Boolean(), nullable=False, server_default='0'))
    
    # Add cancel_requested column
    op.add_column('jobs', sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    # Remove columns
    op.drop_column('jobs', 'cancel_requested')
    op.drop_column('jobs', 'pause_requested')
