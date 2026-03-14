"""Tests for /api/summary/by-month endpoint."""
from datetime import date

from routers import summary, transactions
from schemas import TransactionCreate


def _create_txn(db_session, agent, **overrides):
    payload = {
        "scope": "salon",
        "type": "income",
        "amount": 100.0,
        "category": "haircut",
        "date": date.today().isoformat(),
        "force_create": True,
    }
    payload.update(overrides)
    return transactions.create_transaction(
        TransactionCreate(**payload),
        agent=agent,
        db=db_session,
    )["data"]


def test_by_month_basic(db_session, admin_agent):
    """Create txns across 2 months, verify both months appear with correct totals."""
    _create_txn(db_session, admin_agent, amount=500.0, date="2026-01-15")
    _create_txn(db_session, admin_agent, amount=300.0, date="2026-01-20", force_create=True)
    _create_txn(db_session, admin_agent, amount=200.0, date="2026-02-10")
    _create_txn(
        db_session, admin_agent,
        type="expense", amount=50.0, category="supplies", date="2026-02-10",
        force_create=True,
    )

    resp = summary.get_by_month(
        scope="salon",
        from_date="2026-01-01",
        to_date="2026-02-28",
        payment_method=None,
        source=None,
        agent=admin_agent,
        db=db_session,
    )

    data = resp["data"]
    months = {m["month"]: m for m in data["months"]}

    assert "2026-01" in months
    assert "2026-02" in months
    assert months["2026-01"]["income"] == 800.0
    assert months["2026-01"]["income_count"] == 2
    assert months["2026-01"]["expenses"] == 0.0
    assert months["2026-02"]["income"] == 200.0
    assert months["2026-02"]["expenses"] == 50.0
    assert months["2026-02"]["profit"] == 150.0
    assert resp["meta"]["count"] == 2


def test_by_month_source_filter(db_session, admin_agent):
    """Verify ?source=bank returns only bank (tributary) tx totals."""
    # Bank tx (from tributary)
    _create_txn(
        db_session, admin_agent,
        amount=400.0, date="2026-03-10",
        external_source="tributary", external_id="trib-001",
        payment_method="bank",
    )
    # Cash tx
    _create_txn(
        db_session, admin_agent,
        amount=100.0, date="2026-03-12",
        payment_method="cash",
    )

    resp = summary.get_by_month(
        scope="salon",
        from_date="2026-03-01",
        to_date="2026-03-31",
        payment_method=None,
        source="bank",
        agent=admin_agent,
        db=db_session,
    )

    months = {m["month"]: m for m in resp["data"]["months"]}
    assert months["2026-03"]["income"] == 400.0
    assert months["2026-03"]["income_count"] == 1


def test_by_month_empty_months_filled(db_session, admin_agent):
    """Months with no data should appear in the result with 0s."""
    # Only create data in first and last month of range
    _create_txn(db_session, admin_agent, amount=100.0, date="2026-04-05")
    _create_txn(db_session, admin_agent, amount=200.0, date="2026-06-15", force_create=True)

    resp = summary.get_by_month(
        scope="salon",
        from_date="2026-04-01",
        to_date="2026-06-30",
        payment_method=None,
        source=None,
        agent=admin_agent,
        db=db_session,
    )

    data = resp["data"]
    assert resp["meta"]["count"] == 3  # April, May, June

    months = {m["month"]: m for m in data["months"]}
    assert "2026-04" in months
    assert "2026-05" in months
    assert "2026-06" in months

    # May should be all zeros
    assert months["2026-05"]["income"] == 0.0
    assert months["2026-05"]["expenses"] == 0.0
    assert months["2026-05"]["profit"] == 0.0
    assert months["2026-05"]["income_count"] == 0
    assert months["2026-05"]["expense_count"] == 0

    # April and June should have data
    assert months["2026-04"]["income"] == 100.0
    assert months["2026-06"]["income"] == 200.0
