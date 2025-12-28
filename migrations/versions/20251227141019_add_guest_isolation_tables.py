"""Add guest isolation tables

Revision ID: 20251227141019
Revises: e08bd99be194
Create Date: 2025-12-27 14:10:19.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251227141019'
down_revision = 'e08bd99be194'
branch_labels = None
depends_on = None


def upgrade():
    # Create guest_email_items table
    op.create_table('guest_email_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_normalized', sa.String(length=255), nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column('result', sa.String(length=50), nullable=False),
        sa.Column('matched_email_id', sa.Integer(), nullable=True),
        sa.Column('rejected_reason', sa.String(length=100), nullable=True),
        sa.Column('rejected_details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['matched_email_id'], ['emails.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_id', 'email_normalized', name='uq_guest_batch_email')
    )
    
    with op.batch_alter_table('guest_email_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_guest_email_items_batch_id'), ['batch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_guest_email_items_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_guest_email_items_email_normalized'), ['email_normalized'], unique=False)
        batch_op.create_index(batch_op.f('ix_guest_email_items_domain'), ['domain'], unique=False)
        batch_op.create_index(batch_op.f('ix_guest_email_items_result'), ['result'], unique=False)
        batch_op.create_index(batch_op.f('ix_guest_email_items_matched_email_id'), ['matched_email_id'], unique=False)
        batch_op.create_index('idx_guest_user_batch', ['user_id', 'batch_id'], unique=False)

    # Create guest_download_history table
    op.create_table('guest_download_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=True),
        sa.Column('download_type', sa.String(length=50), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('record_count', sa.Integer(), nullable=False),
        sa.Column('filters', sa.Text(), nullable=True),
        sa.Column('downloaded_times', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_downloaded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    with op.batch_alter_table('guest_download_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_guest_download_history_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_guest_download_history_batch_id'), ['batch_id'], unique=False)


def downgrade():
    # Drop guest_download_history table
    op.drop_table('guest_download_history')
    
    # Drop guest_email_items table
    op.drop_table('guest_email_items')
