"""soft_delete_and_fk_hardening

Revision ID: 5724eca6fd16
Revises: a5d4361f28b5
Create Date: 2026-02-18 02:04:29.687220

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5724eca6fd16'
down_revision: Union[str, Sequence[str], None] = 'a5d4361f28b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    # Preflight cleanup before enforcing foreign keys.
    conn.execute(
        sa.text(
            """
            UPDATE transactions
            SET entity_id = NULL
            WHERE entity_id IS NOT NULL
              AND entity_id NOT IN (SELECT id FROM entities)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE item_movements
            SET transaction_id = NULL
            WHERE transaction_id IS NOT NULL
              AND transaction_id NOT IN (SELECT id FROM transactions)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM item_movements
            WHERE item_id NOT IN (SELECT id FROM items)
            """
        )
    )

    # Soft-delete marker columns.
    with op.batch_alter_table("entities", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.Integer(), nullable=True))
        batch_op.create_index("ix_entities_deleted_at", ["deleted_at"], unique=False)

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.Integer(), nullable=True))
        batch_op.create_index("ix_transactions_deleted_at", ["deleted_at"], unique=False)

    with op.batch_alter_table("items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.Integer(), nullable=True))
        batch_op.create_index("ix_items_deleted_at", ["deleted_at"], unique=False)

    with op.batch_alter_table("services", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.Integer(), nullable=True))
        batch_op.create_index("ix_services_deleted_at", ["deleted_at"], unique=False)

    with op.batch_alter_table("list_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.Integer(), nullable=True))
        batch_op.create_index("ix_list_items_deleted_at", ["deleted_at"], unique=False)

    # Add foreign keys with SQLite-safe table recreation.
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.create_foreign_key(
            "fk_transactions_entity_id_entities",
            "entities",
            ["entity_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("item_movements", recreate="always") as batch_op:
        batch_op.create_foreign_key(
            "fk_item_movements_item_id_items",
            "items",
            ["item_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_item_movements_transaction_id_transactions",
            "transactions",
            ["transaction_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("item_movements", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "fk_item_movements_transaction_id_transactions",
            type_="foreignkey",
        )
        batch_op.drop_constraint("fk_item_movements_item_id_items", type_="foreignkey")

    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "fk_transactions_entity_id_entities",
            type_="foreignkey",
        )

    with op.batch_alter_table("list_items", schema=None) as batch_op:
        batch_op.drop_index("ix_list_items_deleted_at")
        batch_op.drop_column("deleted_at")

    with op.batch_alter_table("services", schema=None) as batch_op:
        batch_op.drop_index("ix_services_deleted_at")
        batch_op.drop_column("deleted_at")

    with op.batch_alter_table("items", schema=None) as batch_op:
        batch_op.drop_index("ix_items_deleted_at")
        batch_op.drop_column("deleted_at")

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_index("ix_transactions_deleted_at")
        batch_op.drop_column("deleted_at")

    with op.batch_alter_table("entities", schema=None) as batch_op:
        batch_op.drop_index("ix_entities_deleted_at")
        batch_op.drop_column("deleted_at")
