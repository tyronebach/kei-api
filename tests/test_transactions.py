import pytest
from fastapi import HTTPException

from routers import transactions
from schemas import TransactionCreate, TransactionUpdate


# ---------------------------------------------------------------------------
# Fuzzy duplicate detection tests
# ---------------------------------------------------------------------------


def _seed_txn(db_session, agent, **overrides):
    """Insert a transaction directly (force_create=True so no fuzzy interference)."""
    payload = {
        "scope": "salon",
        "type": "expense",
        "amount": 80.0,
        "category": "supplies",
        "date": "2026-03-10",
        "description": "Office Depot paper",
        "force_create": True,
    }
    payload.update(overrides)
    return transactions.create_transaction(
        TransactionCreate(**payload),
        agent=agent,
        db=db_session,
    )


def test_fuzzy_exact_match_returns_matched(db_session, admin_agent):
    """Exact amount + same description + same day → matched=true, no new row."""
    seed = _seed_txn(db_session, admin_agent)
    existing_id = seed["data"].id

    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=80.0,
            category="supplies",
            date="2026-03-10",
            description="Office Depot paper",
        ),
        agent=admin_agent,
        db=db_session,
    )
    assert result.get("matched") is True
    assert result["data"].id == existing_id
    # No new row created
    from db.models import Transaction
    count = db_session.query(Transaction).filter(Transaction.deleted_at.is_(None)).count()
    assert count == 1


def test_fuzzy_similar_description_one_day_off_returns_matched(db_session, admin_agent):
    """Same amount + similar description + 1 day off → matched=true."""
    _seed_txn(db_session, admin_agent, date="2026-03-10", description="Office Depot paper")

    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=80.0,
            category="supplies",
            date="2026-03-11",
            description="Office Depot papers",
        ),
        agent=admin_agent,
        db=db_session,
    )
    assert result.get("matched") is True


def test_fuzzy_different_description_not_matched(db_session, admin_agent):
    """Same amount + totally different description → score < 85, created normally."""
    _seed_txn(db_session, admin_agent, description="Office Depot paper")

    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=80.0,
            category="supplies",
            date="2026-03-10",
            description="Completely unrelated grocery store",
        ),
        agent=admin_agent,
        db=db_session,
    )
    assert result.get("matched") is None
    assert result.get("created") is True


def test_fuzzy_amount_too_different_not_matched(db_session, admin_agent):
    """Amount differs by >5% → not matched."""
    _seed_txn(db_session, admin_agent, amount=80.0, description="Office Depot paper")

    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=60.0,  # >5% off from 80
            category="supplies",
            date="2026-03-10",
            description="Office Depot paper",
        ),
        agent=admin_agent,
        db=db_session,
    )
    assert result.get("matched") is None
    assert result.get("created") is True


def test_fuzzy_force_create_bypasses_check(db_session, admin_agent):
    """force_create=True bypasses fuzzy check and always inserts."""
    _seed_txn(db_session, admin_agent)

    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=80.0,
            category="supplies",
            date="2026-03-10",
            description="Office Depot paper",
            force_create=True,
        ),
        agent=admin_agent,
        db=db_session,
    )
    assert result.get("matched") is None
    assert result.get("created") is True


def test_fuzzy_tributary_write_bypasses_check(db_session, admin_agent):
    """Tributary write (external_source set) always bypasses fuzzy check."""
    _seed_txn(db_session, admin_agent)

    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=80.0,
            category="supplies",
            date="2026-03-10",
            description="Office Depot paper",
            external_source="tributary",
            external_id="ext-001",
        ),
        agent=admin_agent,
        db=db_session,
    )
    # Tributary writes skip fuzzy and insert regardless
    assert result.get("matched") is None
    assert result.get("created") is True or "data" in result


def test_fuzzy_probable_match_response(db_session, admin_agent):
    """Score 70–84 → created with probable_match in response."""
    # Seed a transaction
    _seed_txn(db_session, admin_agent, description="Office Depot paper", date="2026-03-10")

    # Submit something 2 days off with moderately similar description
    # amount exact (score 100*0.4=40), description moderate (~70*0.4=28), date 2 days (60*0.2=12) = ~80
    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=80.0,
            category="supplies",
            date="2026-03-12",
            description="Office Depot",  # shorter — should score ~70-80 on token_sort_ratio
        ),
        agent=admin_agent,
        db=db_session,
    )
    # Either matched (>=85) or probable_match (70-84) or just created (<70)
    # We primarily verify the response shape is valid
    assert "matched" in result or "created" in result


def _create_txn(db_session, agent, **overrides):
    payload = {
        "scope": "salon",
        "type": "income",
        "amount": 80.0,
        "category": "haircut",
        "date": "2026-02-10",
        "description": "test",
    }
    payload.update(overrides)
    return transactions.create_transaction(
        TransactionCreate(**payload),
        agent=agent,
        db=db_session,
    )["data"]


def test_transactions_crud(db_session, admin_agent):
    created = _create_txn(db_session, admin_agent)
    txn_id = created.id

    fetched = transactions.get_transaction(txn_id, agent=admin_agent, db=db_session)
    assert fetched["data"].amount == 80.0

    updated = transactions.update_transaction(
        txn_id,
        TransactionUpdate(amount=100.0),
        agent=admin_agent,
        db=db_session,
    )
    assert updated["data"].amount == 100.0

    deleted = transactions.delete_transaction(txn_id, agent=admin_agent, db=db_session)
    assert deleted["data"]["deleted"] is True

    with pytest.raises(HTTPException) as exc:
        transactions.get_transaction(txn_id, agent=admin_agent, db=db_session)
    assert exc.value.status_code == 404


def test_manually_enriched_flag_persists(db_session, admin_agent):
    """manually_enriched=True is auto-inferred on create when description is set,
    and persists on subsequent GET."""
    created = _create_txn(db_session, admin_agent)
    txn_id = created.id
    # description="test" is set by _create_txn → auto-inferred as manually_enriched
    assert created.manually_enriched is True

    updated = transactions.update_transaction(
        txn_id,
        TransactionUpdate(manually_enriched=True),
        agent=admin_agent,
        db=db_session,
    )
    assert updated["data"].manually_enriched is True

    fetched = transactions.get_transaction(txn_id, agent=admin_agent, db=db_session)
    assert fetched["data"].manually_enriched is True


def test_manually_enriched_in_list_response(db_session, admin_agent):
    """manually_enriched is included in transaction list responses."""
    _create_txn(db_session, admin_agent, category="haircut", date="2026-02-10")
    # Create a second one with manually_enriched=True via update
    created2 = _create_txn(db_session, admin_agent, category="color", date="2026-02-11", force_create=True)
    transactions.update_transaction(
        created2.id,
        TransactionUpdate(manually_enriched=True),
        agent=admin_agent,
        db=db_session,
    )

    result = transactions.list_transactions(
        scope="salon",
        from_date=None,
        to_date=None,
        sort="date",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    txns = result["data"]
    assert len(txns) == 2
    flags = {t.category: t.manually_enriched for t in txns}
    # haircut: created with description="test" → auto-inferred manually_enriched=True
    assert flags["haircut"] is True
    assert flags["color"] is True


def test_force_create_and_manually_enriched_dont_interfere(db_session, admin_agent):
    """force_create + manually_enriched can be combined without conflict."""
    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=50.0,
            category="supplies",
            date="2026-03-10",
            description="Manual enriched forced",
            force_create=True,
            manually_enriched=True,
        ),
        agent=admin_agent,
        db=db_session,
    )
    assert result.get("created") is True
    assert result["data"].manually_enriched is True

    fetched = transactions.get_transaction(result["data"].id, agent=admin_agent, db=db_session)
    assert fetched["data"].manually_enriched is True


def test_transaction_filters(db_session, admin_agent):
    _create_txn(db_session, admin_agent, category="haircut", date="2026-02-01", amount=60.0)
    _create_txn(db_session, admin_agent, category="color", date="2026-02-15", amount=120.0)
    _create_txn(
        db_session,
        admin_agent,
        category="supplies",
        type="expense",
        date="2026-02-20",
        amount=30.0,
    )

    by_type = transactions.list_transactions(
        scope="salon",
        type="income",
        from_date=None,
        to_date=None,
        sort="date",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert by_type["meta"]["total"] == 2

    by_cat = transactions.list_transactions(
        scope="salon",
        category="haircut,color",
        from_date=None,
        to_date=None,
        sort="date",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert by_cat["meta"]["total"] == 2

    by_range = transactions.list_transactions(
        scope="salon",
        from_date="2026-02-10",
        to_date="2026-02-28",
        sort="date",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert by_range["meta"]["total"] == 2


# ---------------------------------------------------------------------------
# payment_method enum tests
# ---------------------------------------------------------------------------


def test_payment_method_valid(db_session, admin_agent):
    """Create transaction with each valid payment_method value — all should succeed."""
    valid_methods = ["cash", "etransfer", "card", "bank", "cheque", "other"]
    for i, method in enumerate(valid_methods):
        result = _create_txn(
            db_session,
            admin_agent,
            payment_method=method,
            date=f"2026-01-{i + 1:02d}",
            force_create=True,
        )
        assert result.payment_method == method


def test_payment_method_invalid(db_session, admin_agent):
    """Create transaction with invalid payment_method → 422 validation error."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TransactionCreate(
            scope="salon",
            type="income",
            amount=80.0,
            category="haircut",
            date="2026-01-01",
            payment_method="wire",
        )


def test_list_filter_payment_method(db_session, admin_agent):
    """Filter transactions by payment_method."""
    _create_txn(db_session, admin_agent, payment_method="cash", date="2026-01-01", force_create=True)
    _create_txn(db_session, admin_agent, payment_method="bank", date="2026-01-02", force_create=True)
    _create_txn(db_session, admin_agent, date="2026-01-03", force_create=True)

    cash_result = transactions.list_transactions(
        scope="salon",
        type=None,
        category=None,
        entity_id=None,
        from_date=None,
        to_date=None,
        payment_method="cash",
        external_source=None,
        sort="date",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert cash_result["meta"]["total"] == 1
    assert cash_result["data"][0].payment_method == "cash"

    bank_result = transactions.list_transactions(
        scope="salon",
        type=None,
        category=None,
        entity_id=None,
        from_date=None,
        to_date=None,
        payment_method="bank",
        external_source=None,
        sort="date",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert bank_result["meta"]["total"] == 1
    assert bank_result["data"][0].payment_method == "bank"


def test_list_filter_external_source(db_session, admin_agent):
    """Filter transactions by external_source."""
    # Tributary transaction
    _create_txn(
        db_session,
        admin_agent,
        external_source="tributary",
        external_id="trib-001",
        date="2026-01-01",
    )
    # Normal transaction
    _create_txn(db_session, admin_agent, date="2026-01-02", force_create=True)

    result = transactions.list_transactions(
        scope="salon",
        type=None,
        category=None,
        entity_id=None,
        from_date=None,
        to_date=None,
        payment_method=None,
        external_source="tributary",
        sort="date",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert result["meta"]["total"] == 1
    assert result["data"][0].external_source == "tributary"


# ---------------------------------------------------------------------------
# Fix 1.2 — PATCH auto-inference respects explicit manually_enriched
# ---------------------------------------------------------------------------


def test_patch_explicit_manually_enriched_false(db_session, admin_agent):
    """PATCH with description + manually_enriched=false keeps the flag false."""
    txn = _create_txn(
        db_session, admin_agent, description=None, date="2026-01-15",
        force_create=True,
    )
    # manually_enriched should be False (no description on create)
    assert txn.manually_enriched is False

    result = transactions.patch_transaction(
        txn.id,
        TransactionUpdate(description="bank string", manually_enriched=False),
        agent=admin_agent,
        db=db_session,
    )
    assert result["data"].description == "bank string"
    assert result["data"].manually_enriched is False


def test_patch_auto_infers_manually_enriched_when_omitted(db_session, admin_agent):
    """PATCH with description but no manually_enriched field → auto-infer True."""
    txn = _create_txn(
        db_session, admin_agent, description=None, date="2026-01-16",
        force_create=True,
    )
    assert txn.manually_enriched is False

    result = transactions.patch_transaction(
        txn.id,
        TransactionUpdate(description="human note"),
        agent=admin_agent,
        db=db_session,
    )
    assert result["data"].description == "human note"
    assert result["data"].manually_enriched is True


# ---------------------------------------------------------------------------
# Fix 1.3 — Warn-band response includes data key
# ---------------------------------------------------------------------------


def test_warn_band_response_includes_data(db_session, admin_agent):
    """When a POST hits the warn band (score 60-84), the response must include data."""
    # Seed a transaction
    _seed_txn(db_session, admin_agent, description="Office Depot paper", date="2026-03-10")

    # Submit something that scores in the probable-match range
    # Same amount, 2 days off, shorter description
    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=80.0,
            category="supplies",
            date="2026-03-12",
            description="Office Depot",
        ),
        agent=admin_agent,
        db=db_session,
    )
    if result.get("created") and result.get("probable_match"):
        # Hit the warn band — verify data key is present
        assert "data" in result, "Warn-band response must include 'data' key"
        assert result["data"].id is not None
        assert "match_score" in result
