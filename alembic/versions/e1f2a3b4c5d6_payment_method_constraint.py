"""payment_method CHECK constraint and index

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-03-14

Changes:
- Add CHECK constraint on transactions.payment_method
- Add index idx_transactions_payment_method
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

_CHECK_CLAUSE = (
    "CHECK(payment_method IN ('cash', 'etransfer', 'card', 'bank', 'cheque', 'other') "
    "OR payment_method IS NULL)"
)


def upgrade() -> None:
    conn = op.get_bind()

    # Drop any leftover temp table from prior failed attempts.
    conn.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_transactions"))

    # Retrieve current CREATE TABLE SQL
    create_sql_row = conn.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type='table' AND name='transactions'")
    ).fetchone()

    if create_sql_row:
        old_sql = create_sql_row[0]

        # The SQL may have the table name quoted ("transactions") or unquoted.
        # Replace the table name with our temp name regardless of quoting.
        new_sql = re.sub(
            r'CREATE TABLE\s+"?transactions"?',
            "CREATE TABLE _alembic_tmp_transactions",
            old_sql,
            count=1,
        )

        # Inject CHECK constraint before the closing paren
        new_sql = new_sql.rstrip().rstrip(")").rstrip() + f",\n    {_CHECK_CLAUSE}\n)"

        conn.execute(sa.text(new_sql))
        conn.execute(sa.text("INSERT INTO _alembic_tmp_transactions SELECT * FROM transactions"))
        conn.execute(sa.text("DROP TABLE transactions"))
        conn.execute(sa.text("ALTER TABLE _alembic_tmp_transactions RENAME TO transactions"))

    # Recreate indexes that were dropped when we replaced the table.
    existing_idxs = {
        row[1]
        for row in conn.execute(sa.text("PRAGMA index_list('transactions')"))
    }

    if "uq_transactions_external_identity" not in existing_idxs:
        op.create_index(
            "uq_transactions_external_identity",
            "transactions",
            ["external_source", "external_id"],
            unique=True,
        )

    if "idx_transactions_payment_method" not in existing_idxs:
        op.create_index(
            "idx_transactions_payment_method",
            "transactions",
            ["payment_method"],
        )


def downgrade() -> None:
    op.drop_index("idx_transactions_payment_method", table_name="transactions")

    # Remove CHECK constraint by recreating table without it
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        pass
