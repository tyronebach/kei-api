"""Tests for Step 2: external transaction identity (idempotent ingest)."""
import pytest
from fastapi import HTTPException

from routers import transactions
from schemas import TransactionCreate


def _make_body(**overrides):
    payload = {
        "scope": "home",
        "type": "expense",
        "amount": 42.50,
        "category": "groceries",
        "date": "2026-03-12",
    }
    payload.update(overrides)
    return TransactionCreate(**payload)


def test_same_external_identity_returns_existing_row(db_session, admin_agent):
    """POSTing the same (external_source, external_id) twice must return the same row."""
    body = _make_body(external_source="tributary", external_id="txn-abc-123")

    first = transactions.create_transaction(body, agent=admin_agent, db=db_session)
    second = transactions.create_transaction(body, agent=admin_agent, db=db_session)

    assert first["data"].id == second["data"].id

    # Confirm only one row in DB
    all_txns = transactions.list_transactions(
        scope="home",
        type="expense",
        from_date=None,
        to_date=None,
        sort="date",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert all_txns["meta"]["total"] == 1


def test_normal_write_without_external_identity(db_session, admin_agent):
    """Normal writes (no external identity) with distinct amounts create distinct rows."""
    body1 = _make_body(amount=42.50)
    body2 = _make_body(amount=99.00)  # different amount → fails 5% gate → below fuzzy threshold

    first = transactions.create_transaction(body1, agent=admin_agent, db=db_session)
    second = transactions.create_transaction(body2, agent=admin_agent, db=db_session)

    assert first["data"].id != second["data"].id

    all_txns = transactions.list_transactions(
        scope="home",
        type="expense",
        from_date=None,
        to_date=None,
        sort="date",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert all_txns["meta"]["total"] == 2


def test_identical_manual_writes_warn_band(db_session, admin_agent):
    """Identical manual writes (same date/amount, no description) hit the warn band.

    Null+null description scores 50 (ambiguous). Total = 100*0.4 + 50*0.4 + 100*0.2 = 80.
    Hard block threshold is ≥92 — so both writes succeed but second carries a probable_match warning.
    """
    body = _make_body()

    first = transactions.create_transaction(body, agent=admin_agent, db=db_session)
    second = transactions.create_transaction(body, agent=admin_agent, db=db_session)

    assert first.get("data") is not None, "First write should succeed"
    # Score 80 → warn band: written (created=True) but probable_match returned (no data key)
    assert second.get("created") is True, "Second write should be recorded (warn band, not blocked)"
    assert second.get("probable_match") is not None, "Should carry a probable_match warning"
    assert second["match_score"] == 80

def test_identical_manual_writes_with_description_hard_blocked(db_session, admin_agent):
    """Identical manual writes WITH matching description hit the hard block (score ≥92)."""
    body = _make_body(description="Kevin - haircut")

    first = transactions.create_transaction(body, agent=admin_agent, db=db_session)
    second = transactions.create_transaction(body, agent=admin_agent, db=db_session)

    assert first.get("data") is not None, "First write should succeed"
    assert second.get("matched") is True, "Second identical write with description should be hard-blocked"


def test_external_identity_must_be_paired(db_session, admin_agent):
    """Providing only external_source (without external_id) must be rejected."""
    with pytest.raises(Exception):
        _make_body(external_source="tributary")  # missing external_id


def test_amount_roundtrip_cents(db_session, admin_agent):
    """Amount should round-trip through cents without float drift."""
    body = _make_body(amount=99.99)
    result = transactions.create_transaction(body, agent=admin_agent, db=db_session)
    assert result["data"].amount == 99.99
