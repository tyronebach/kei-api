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


def run_alembic(db_path: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "KEI_DATABASE_URL": f"sqlite:///{db_path}",
        "KEI_API_TOKEN": "test-token",
        "KEI_ALLOW_INSECURE_DEFAULT_TOKEN": "true",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def run_alembic_upgrade(db_path: str) -> None:
    """Run `alembic upgrade head` against a temporary DB path."""
    result = run_alembic(db_path, "upgrade", "head")
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )


def _table_exists(db_path: Path, table: str) -> bool:
    engine = sa.create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            return (
                conn.execute(
                    sa.text(
                        "SELECT 1 FROM sqlite_master "
                        "WHERE type='table' AND name=:table"
                    ),
                    {"table": table},
                ).fetchone()
                is not None
            )
    finally:
        engine.dispose()


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


def _get_index_columns(engine, table: str, index: str) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(sa.text(f"PRAGMA index_info('{index}')")).fetchall()
    return [row[2] for row in rows]


def _get_foreign_keys(engine, table: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(sa.text(f"PRAGMA foreign_key_list('{table}')")).fetchall()
    return [
        {
            "table": row[2],
            "from": row[3],
            "to": row[4],
            "on_delete": row[6],
        }
        for row in rows
    ]


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
    assert _get_index_columns(
        migrated_engine,
        "transactions",
        "uq_transactions_external_identity",
    ) == ["external_source", "external_id"]


def test_transactions_amount_is_integer(migrated_engine):
    cols = _get_columns(migrated_engine, "transactions")
    assert "amount" in cols
    # SQLite stores types loosely; check the declared type contains INTEGER
    col_type = cols["amount"]["type"].upper()
    assert "INT" in col_type, f"Expected INTEGER type for amount, got: {col_type}"


def test_payment_method_constraint_downgrade_fails_loudly(tmp_path):
    db_path = tmp_path / "downgrade.db"
    upgrade_result = run_alembic(str(db_path), "upgrade", "e1f2a3b4c5d6")
    assert upgrade_result.returncode == 0

    result = run_alembic(str(db_path), "downgrade", "d1e2f3a4b5c6")

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Downgrade e1f2a3b4c5d6 is unsupported" in output
    assert "payment_method CHECK constraint" in output


def test_alembic_current_still_works_with_downgrade_guard(tmp_path):
    db_path = tmp_path / "current.db"
    run_alembic_upgrade(str(db_path))

    result = run_alembic(str(db_path), "current")

    assert result.returncode == 0
    assert "73fc7456f3d0" in result.stdout


@pytest.mark.parametrize("target", ["d1e2f3a4b5c6", "-2"])
def test_payment_method_constraint_downgrade_from_head_fails_before_later_changes(
    tmp_path,
    target,
):
    db_path = tmp_path / f"downgrade-head-{target}.db"
    run_alembic_upgrade(str(db_path))

    result = run_alembic(str(db_path), "downgrade", target)

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Downgrade across e1f2a3b4c5d6 is unsupported" in output
    assert _table_exists(db_path, "snapshots")


def test_snapshots_have_unique_scope_date_constraint(migrated_engine):
    idxs = _get_indexes(migrated_engine, "snapshots")
    unique_indexes = [name for name, info in idxs.items() if info["unique"]]
    assert any(
        _get_index_columns(migrated_engine, "snapshots", index) == ["scope", "date"]
        for index in unique_indexes
    ), "snapshots must enforce unique (scope, date)"


def test_snapshots_have_scope_and_date_indexes(migrated_engine):
    idxs = _get_indexes(migrated_engine, "snapshots")
    assert "idx_snapshots_scope" in idxs
    assert "idx_snapshots_date" in idxs


def test_item_movements_have_expected_foreign_keys(migrated_engine):
    fks = _get_foreign_keys(migrated_engine, "item_movements")
    assert {
        "table": "items",
        "from": "item_id",
        "to": "id",
        "on_delete": "CASCADE",
    } in fks
    assert {
        "table": "transactions",
        "from": "transaction_id",
        "to": "id",
        "on_delete": "SET NULL",
    } in fks


def test_agent_tokens_have_unique_identity_indexes(migrated_engine):
    idxs = _get_indexes(migrated_engine, "agent_tokens")
    unique_index_columns = [
        _get_index_columns(migrated_engine, "agent_tokens", index)
        for index, info in idxs.items()
        if info["unique"]
    ]
    assert ["agent_id"] in unique_index_columns
    assert ["token_hash"] in unique_index_columns


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
