"""agent_tokens_and_actor_attribution

Revision ID: 7af2e8e2bb4f
Revises: 5724eca6fd16
Create Date: 2026-02-18 02:13:46.085529

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7af2e8e2bb4f'
down_revision: Union[str, Sequence[str], None] = '5724eca6fd16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("allowed_scopes", sa.JSON(), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id"),
        sa.UniqueConstraint("token_hash"),
    )

    for table_name in ("entities", "transactions", "items", "services", "list_items"):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.add_column(sa.Column("created_by", sa.String(), nullable=True))
            batch_op.add_column(sa.Column("updated_by", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    for table_name in ("list_items", "services", "items", "transactions", "entities"):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_column("updated_by")
            batch_op.drop_column("created_by")

    op.drop_table("agent_tokens")
