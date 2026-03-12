"""hardening: remove recurring, add external identity, amount to cents

Revision ID: c1d2e3f4a5b6
Revises: b3f1a2c4d5e6
Create Date: 2026-03-12

Changes:
- Drop recurring_rules and recurring_skips tables (IF EXISTS)
- Remove rule_id, rule_date columns from transactions
- Add external_source, external_id columns to transactions (with unique index)
- Convert transactions.amount from Float to Integer cents
"""
from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "b3f1a2c4d5e6"
branch_labels = None
depends_on = None


def _get_col_names(conn, table: str) -> list[str]:
    return [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info('{table}')"))]


def _get_idx_names(conn, table: str) -> list[str]:
    return [row[1] for row in conn.execute(sa.text(f"PRAGMA index_list('{table}')"))]


def upgrade() -> None:
    conn = op.get_bind()

    # 0. Clean up any leftover Alembic temp table from prior failed attempts.
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_transactions"))

    # 1. Drop recurring tables if they exist.
    conn.execute(sa.text("DROP TABLE IF EXISTS recurring_skips"))
    conn.execute(sa.text("DROP TABLE IF EXISTS recurring_rules"))

    # 2. Remove recurring columns, add external identity columns.
    #    Use batch_op.drop_index inside the context so Alembic knows not to recreate it.
    existing_cols = _get_col_names(conn, "transactions")
    existing_idxs = _get_idx_names(conn, "transactions")

    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        # Drop rule_id index before dropping the column
        if "idx_transactions_rule" in existing_idxs:
            batch_op.drop_index("idx_transactions_rule")
        if "rule_id" in existing_cols:
            batch_op.drop_column("rule_id")
        if "rule_date" in existing_cols:
            batch_op.drop_column("rule_date")
        if "external_source" not in existing_cols:
            batch_op.add_column(sa.Column("external_source", sa.String, nullable=True))
        if "external_id" not in existing_cols:
            batch_op.add_column(sa.Column("external_id", sa.String, nullable=True))

    # 3. Convert amount Float → Integer cents.
    #    a) Add amount_cents column (nullable for the UPDATE step).
    existing_cols2 = _get_col_names(conn, "transactions")
    if "amount_cents" not in existing_cols2:
        conn.execute(sa.text("ALTER TABLE transactions ADD COLUMN amount_cents INTEGER"))
    conn.execute(sa.text(
        "UPDATE transactions "
        "SET amount_cents = CAST(ROUND(amount * 100) AS INTEGER) "
        "WHERE amount_cents IS NULL"
    ))

    #    b) Recreate table: drop old amount Float, rename amount_cents → amount Integer.
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_column("amount")
        batch_op.alter_column(
            "amount_cents",
            new_column_name="amount",
            nullable=False,
            type_=sa.Integer,
        )

    # 4. Add unique index on (external_source, external_id).
    op.create_index(
        "uq_transactions_external_identity",
        "transactions",
        ["external_source", "external_id"],
        unique=True,
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Drop external identity index
    op.drop_index("uq_transactions_external_identity", table_name="transactions")

    # Convert Integer cents → Float dollars
    conn.execute(sa.text("ALTER TABLE transactions ADD COLUMN amount_dollars REAL"))
    conn.execute(sa.text("UPDATE transactions SET amount_dollars = amount / 100.0"))
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_column("amount")
        batch_op.alter_column(
            "amount_dollars",
            new_column_name="amount",
            nullable=False,
            type_=sa.Float,
        )

    # Remove external identity columns
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_column("external_source")
        batch_op.drop_column("external_id")

    # Restore recurring linkage columns
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("rule_id", sa.String))
        batch_op.add_column(sa.Column("rule_date", sa.String))
        batch_op.create_index("idx_transactions_rule", ["rule_id"])

    # Recreate recurring tables
    op.create_table(
        "recurring_rules",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("scope", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("frequency", sa.String, nullable=False),
        sa.Column("interval", sa.Integer, nullable=False, server_default="1"),
        sa.Column("day_of_month", sa.Integer),
        sa.Column("start_date", sa.String, nullable=False),
        sa.Column("end_date", sa.String),
        sa.Column("description", sa.Text),
        sa.Column("entity_id", sa.String),
        sa.Column("payment_method", sa.String),
        sa.Column("tags", sa.JSON),
        sa.Column("meta", sa.JSON),
        sa.Column("created_by", sa.String),
        sa.Column("updated_by", sa.String),
        sa.Column("deleted_at", sa.Integer),
        sa.Column("created_at", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.Integer, nullable=False),
    )

    op.create_table(
        "recurring_skips",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("rule_id", sa.String, nullable=False),
        sa.Column("skip_date", sa.String, nullable=False),
        sa.Column("created_at", sa.Integer, nullable=False),
        sa.UniqueConstraint("rule_id", "skip_date", name="uq_recurring_skip_rule_date"),
    )
