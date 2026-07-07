"""add_users_queue_and_config

Revision ID: a8d8e52e4e1a
Revises: 401aa3559d21
Create Date: 2026-07-07 19:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8d8e52e4e1a'
down_revision: Union[str, None] = '401aa3559d21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns to channels
    op.add_column('channels', sa.Column('custom_footer', sa.String(), nullable=True))
    op.add_column('channels', sa.Column('auto_pin_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('channels', sa.Column('queue_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('channels', sa.Column('queue_interval_minutes', sa.Integer(), nullable=False, server_default='15'))

    # 2. Create users table
    op.create_table('users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('username', sa.String(), nullable=True),
    sa.Column('first_name', sa.String(), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_user_id'), 'users', ['user_id'], unique=True)

    # 3. Create queue_posts table
    op.create_table('queue_posts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('channel_id', sa.Integer(), nullable=False),
    sa.Column('message_data', sa.String(), nullable=False),
    sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_processed', sa.Boolean(), nullable=False, server_default='false'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('queue_posts')
    op.drop_index(op.f('ix_users_user_id'), table_name='users')
    op.drop_table('users')
    op.drop_column('channels', 'queue_interval_minutes')
    op.drop_column('channels', 'queue_enabled')
    op.drop_column('channels', 'auto_pin_enabled')
    op.drop_column('channels', 'custom_footer')
