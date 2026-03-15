"""add manually_enriched flag to transactions

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-03-11

Changes:
- Add manually_enriched column to transactions (INTEGER, default 0)
"""
from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def _get_col_names(conn, table: str) -> list[str]:
    return [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info('{table}')"))]


def upgrade() -> None:
    conn = op.get_bind()
    existing_cols = _get_col_names(conn, "transactions")
    if "manually_enriched" not in existing_cols:
        conn.execute(sa.text(
            "ALTER TABLE transactions ADD COLUMN manually_enriched INTEGER NOT NULL DEFAULT 0"
        ))
    # Backfill: mark existing human-enriched rows (non-external with description or entity)
    conn.execute(sa.text(
        "UPDATE transactions SET manually_enriched = 1 "
        "WHERE deleted_at IS NULL AND external_source IS NULL "
        "AND (description IS NOT NULL OR entity_id IS NOT NULL)"
    ))


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN in older versions; use batch_alter_table
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        batch_op.drop_column("manually_enriched")
