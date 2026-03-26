"""add_snapshots_table

Revision ID: 73fc7456f3d0
Revises: e1f2a3b4c5d6
Create Date: 2026-03-25 23:32:37.130954

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '73fc7456f3d0'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('snapshots',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('scope', sa.String(), nullable=False),
        sa.Column('date', sa.String(), nullable=False),
        sa.Column('data', sqlite.JSON(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scope', 'date', name='uq_snapshots_scope_date')
    )
    with op.batch_alter_table('snapshots', schema=None) as batch_op:
        batch_op.create_index('idx_snapshots_date', ['date'], unique=False)
        batch_op.create_index('idx_snapshots_scope', ['scope'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('snapshots', schema=None) as batch_op:
        batch_op.drop_index('idx_snapshots_scope')
        batch_op.drop_index('idx_snapshots_date')
    op.drop_table('snapshots')
