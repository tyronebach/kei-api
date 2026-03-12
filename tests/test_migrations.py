"""Step 7: Alembic migration parity test.

Boots a fresh temp SQLite DB via Alembic migrations (not Base.metadata.create_all())
and verifies key schema invariants established by the hardening migration.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[1]


def run_alembic_upgrade(db_path: str) -> None:
    """Run `alembic upgrade head` against a temporary DB path."""
    env = {
        **os.environ,
        "KEI_DATABASE_URL": f"sqlite:///{db_path}",
        "KEI_API_TOKEN": "test-token",
        "KEI_ALLOW_INSECURE_DEFAULT_TOKEN": "true",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )


@pytest.fixture(scope="module")
def migrated_engine():
    """Spin up a fresh DB via Alembic migrations and return a connected engine."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        run_alembic_upgrade(db_path)
        engine = sa.create_engine(f"sqlite:///{db_path}")
        yield engine
        engine.dispose()
    finally:
        os.unlink(db_path)


def _get_columns(engine, table: str) -> dict[str, dict]:
    """Return {column_name: column_info} for a table."""
    with engine.connect() as conn:
        rows = conn.execute(sa.text(f"PRAGMA table_info('{table}')")).fetchall()
    return {row[1]: {"type": row[2], "notnull": row[3], "pk": row[5]} for row in rows}


def _get_indexes(engine, table: str) -> dict[str, dict]:
    """Return {index_name: index_info} for a table."""
    with engine.connect() as conn:
        rows = conn.execute(sa.text(f"PRAGMA index_list('{table}')")).fetchall()
    return {row[1]: {"unique": bool(row[2])} for row in rows}


def test_transactions_has_external_source_column(migrated_engine):
    cols = _get_columns(migrated_engine, "transactions")
    assert "external_source" in cols, "external_source column missing from transactions"


def test_transactions_has_external_id_column(migrated_engine):
    cols = _get_columns(migrated_engine, "transactions")
    assert "external_id" in cols, "external_id column missing from transactions"


def test_transactions_has_unique_external_identity_index(migrated_engine):
    idxs = _get_indexes(migrated_engine, "transactions")
    assert "uq_transactions_external_identity" in idxs, (
        "uq_transactions_external_identity index missing"
    )
    assert idxs["uq_transactions_external_identity"]["unique"], (
        "uq_transactions_external_identity is not unique"
    )


def test_transactions_amount_is_integer(migrated_engine):
    cols = _get_columns(migrated_engine, "transactions")
    assert "amount" in cols
    # SQLite stores types loosely; check the declared type contains INTEGER
    col_type = cols["amount"]["type"].upper()
    assert "INT" in col_type, f"Expected INTEGER type for amount, got: {col_type}"


def test_recurring_tables_do_not_exist(migrated_engine):
    with migrated_engine.connect() as conn:
        tables = [
            row[0]
            for row in conn.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        ]
    assert "recurring_rules" not in tables, "recurring_rules table should not exist"
    assert "recurring_skips" not in tables, "recurring_skips table should not exist"


def test_transactions_no_rule_id_column(migrated_engine):
    cols = _get_columns(migrated_engine, "transactions")
    assert "rule_id" not in cols, "rule_id column should have been removed"
    assert "rule_date" not in cols, "rule_date column should have been removed"
