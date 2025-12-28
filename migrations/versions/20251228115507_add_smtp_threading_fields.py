"""add smtp threading fields

Revision ID: 20251228115507
Revises: 20251227234614
Create Date: 2025-12-28 11:55:07.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251228115507'
down_revision = '20251227234614'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to smtp_configs table
    op.add_column('smtp_configs', sa.Column('thread_count', sa.Integer(), nullable=True))
    op.add_column('smtp_configs', sa.Column('enable_rotation', sa.Boolean(), nullable=True))
    op.add_column('smtp_configs', sa.Column('last_used_at', sa.DateTime(), nullable=True))
    
    # Set default values for existing records
    op.execute("UPDATE smtp_configs SET thread_count = 5 WHERE thread_count IS NULL")
    op.execute("UPDATE smtp_configs SET enable_rotation = true WHERE enable_rotation IS NULL")
    
    # Make thread_count non-nullable after setting defaults
    op.alter_column('smtp_configs', 'thread_count', nullable=False)
    op.alter_column('smtp_configs', 'enable_rotation', nullable=False, server_default='true')


def downgrade():
    # Remove the added columns
    op.drop_column('smtp_configs', 'last_used_at')
    op.drop_column('smtp_configs', 'enable_rotation')
    op.drop_column('smtp_configs', 'thread_count')
