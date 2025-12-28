"""add smtp config and user permission

Revision ID: 20251227234614
Revises: 20251227141019
Create Date: 2025-12-27 23:46:14.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251227234614'
down_revision = '20251227141019'
branch_labels = None
depends_on = None


def upgrade():
    # Add smtp_verification_allowed field to users table
    op.add_column('users', sa.Column('smtp_verification_allowed', sa.Boolean(), nullable=False, server_default='false'))
    
    # Create smtp_configs table
    op.create_table('smtp_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('smtp_host', sa.String(length=255), nullable=False),
        sa.Column('smtp_port', sa.Integer(), nullable=False),
        sa.Column('smtp_username', sa.String(length=255), nullable=True),
        sa.Column('smtp_password', sa.String(length=255), nullable=True),
        sa.Column('use_tls', sa.Boolean(), nullable=False),
        sa.Column('use_ssl', sa.Boolean(), nullable=False),
        sa.Column('from_email', sa.String(length=255), nullable=False),
        sa.Column('timeout', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('last_tested', sa.DateTime(), nullable=True),
        sa.Column('test_status', sa.String(length=50), nullable=True),
        sa.Column('test_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    # Drop smtp_configs table
    op.drop_table('smtp_configs')
    
    # Remove smtp_verification_allowed field from users table
    op.drop_column('users', 'smtp_verification_allowed')
