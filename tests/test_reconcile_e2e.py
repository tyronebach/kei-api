"""End-to-end reconcile scenario tests (Phase 2, item 2.2).

Covers the full Tributary ↔ Rem lifecycle: reconciliation, enrichment,
warn-band response shape, and PATCH auto-inference boundaries.
"""
from db.models import Transaction
from routers import transactions
from schemas import TransactionCreate, TransactionUpdate


def _seed(db_session, agent, **overrides):
    """Insert a transaction with force_create to bypass dedup."""
    payload = {
        "scope": "salon",
        "type": "expense",
        "amount": 50.0,
        "category": "supplies",
        "date": "2026-04-10",
        "force_create": True,
    }
    payload.update(overrides)
    return transactions.create_transaction(
        TransactionCreate(**payload),
        agent=agent,
        db=db_session,
    )


# ---------------------------------------------------------------------------
# Scenario A: Rem first, Tributary later (reconcile)
# ---------------------------------------------------------------------------


def test_scenario_a_rem_first_tributary_claims(db_session, admin_agent):
    """Rem creates a manually-enriched row. Tributary POST with same
    amount/scope/date claims it (reconciled=True), no new row created."""
    # Step 1: Rem creates with description + entity not set (no entity needed)
    rem_result = _seed(
        db_session, admin_agent,
        description="Office paper order",
        date="2026-04-10",
        force_create=True,
    )
    rem_id = rem_result["data"].id
    assert rem_result["data"].manually_enriched is True  # auto-inferred

    # Step 2: Tributary POSTs same amount, same scope, same date
    trib_result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=50.0,
            category="supplies",
            date="2026-04-10",
            external_source="tributary",
            external_id="trib_123",
        ),
        agent=admin_agent,
        db=db_session,
    )

    # Assert reconciliation
    assert trib_result.get("reconciled") is True, f"Expected reconciled=True, got {trib_result}"
    assert trib_result["data"].id == rem_id  # same row, not a new one
    assert trib_result["data"].external_source == "tributary"
    assert trib_result["data"].external_id == "trib_123"
    # Original description preserved
    assert trib_result["data"].description == "Office paper order"

    # No duplicate created
    count = db_session.query(Transaction).filter(Transaction.deleted_at.is_(None)).count()
    assert count == 1


def test_scenario_a_one_day_apart_still_reconciles(db_session, admin_agent):
    """Tributary ±1 day from Rem row still reconciles (score 91 ≥ 85)."""
    _seed(
        db_session, admin_agent,
        description="Paper",
        date="2026-04-10",
    )

    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=50.0,
            category="supplies",
            date="2026-04-11",  # +1 day → score ≈ 91
            external_source="tributary",
            external_id="trib_124",
        ),
        agent=admin_agent,
        db=db_session,
    )
    assert result.get("reconciled") is True


# ---------------------------------------------------------------------------
# Scenario B: Tributary first, Rem later (enrichment)
# ---------------------------------------------------------------------------


def test_scenario_b_tributary_first_rem_enriches(db_session, admin_agent):
    """Tributary imports a row with a bank description. Rem POSTs same
    amount/scope/date with matching description + entity_id. The Tributary
    row is enriched (entity_id added), no duplicate created.

    Note: the Rem fuzzy scorer requires description similarity ≥92% total
    to trigger enrichment. A Tributary row with no description scores 60
    (one-null desc = 0 pts), which falls in the warn band, not enrichment.
    So this test uses a matching description on both sides — the realistic
    scenario where Plaid provides a bank string and Rem's description is
    similar enough to match.
    """
    # Tributary creates with bank-style description, no entity_id
    trib_result = _seed(
        db_session, admin_agent,
        description="OFFICE DEPOT #1234",
        external_source="tributary",
        external_id="trib_456",
        date="2026-04-15",
        force_create=True,
    )
    trib_id = trib_result["data"].id
    assert trib_result["data"].entity_id is None

    # Rem POSTs with similar description + entity_id
    # Need an entity in scope for entity_id validation
    from routers import entities
    from schemas import EntityCreate
    entity = entities.create_entity(
        EntityCreate(scope="salon", name="Office Depot"),
        agent=admin_agent,
        db=db_session,
    )
    entity_id = entity["data"].id

    rem_result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=50.0,
            category="supplies",
            date="2026-04-15",
            description="OFFICE DEPOT #1234",
            entity_id=entity_id,
        ),
        agent=admin_agent,
        db=db_session,
    )

    assert rem_result.get("enriched") is True, f"Expected enriched=True, got {rem_result}"
    assert rem_result["data"].id == trib_id
    assert rem_result["data"].entity_id == entity_id
    assert rem_result["data"].manually_enriched is True

    # No duplicate
    count = db_session.query(Transaction).filter(Transaction.deleted_at.is_(None)).count()
    assert count == 1


def test_scenario_b_tributary_no_desc_rem_with_desc_hits_warn_band(db_session, admin_agent):
    """When Tributary has no description and Rem has one, the fuzzy score
    is only 60 (one-null desc = 0 pts). This lands in the warn band, not
    the enrichment threshold. Verify the system creates a new row with
    probable_match rather than enriching."""
    _seed(
        db_session, admin_agent,
        description=None,
        external_source="tributary",
        external_id="trib_457",
        date="2026-04-16",
        force_create=True,
    )

    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=50.0,
            category="supplies",
            date="2026-04-16",
            description="Human entered note",
        ),
        agent=admin_agent,
        db=db_session,
    )

    # Score = 40 (amount) + 0 (one-null desc) + 20 (same day) = 60 → warn band
    assert result.get("enriched") is None, "Should not enrich at score 60"
    assert result.get("created") is True
    assert "probable_match" in result
    assert "match_score" in result


# ---------------------------------------------------------------------------
# Warn-band response shape
# ---------------------------------------------------------------------------


def test_warn_band_response_has_all_three_keys(db_session, admin_agent):
    """Warn-band response (score 60-84) must contain data, probable_match,
    and match_score — all three keys."""
    # Seed a row with a description
    _seed(
        db_session, admin_agent,
        description="Office supplies run",
        date="2026-04-20",
    )

    # POST with same amount, same day, but no description (one-null → desc_score=0)
    # Score: 40 (amount) + 0 (desc) + 20 (date) = 60 → warn band
    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=50.0,
            category="supplies",
            date="2026-04-20",
            description=None,
        ),
        agent=admin_agent,
        db=db_session,
    )

    assert result.get("created") is True, f"Expected created=True, got {result}"
    assert "data" in result, "Warn-band response must include 'data'"
    assert "probable_match" in result, "Warn-band response must include 'probable_match'"
    assert "match_score" in result, "Warn-band response must include 'match_score'"
    assert 60 <= result["match_score"] <= 84, f"Score {result['match_score']} outside warn band"
    assert result["data"].id is not None
    assert result["probable_match"].id is not None
    assert result["data"].id != result["probable_match"].id


def test_warn_band_tributary_path(db_session, admin_agent):
    """Tributary warn-band (score 60-84) also returns data + probable_match + match_score."""
    # Seed a manually-enriched Rem row
    _seed(
        db_session, admin_agent,
        description="Hair supplies",
        date="2026-04-22",
    )

    # Tributary POST, +2 days → score = 67 (amount) + 16 (date) = 83 → warn band
    result = transactions.create_transaction(
        TransactionCreate(
            scope="salon",
            type="expense",
            amount=50.0,
            category="supplies",
            date="2026-04-24",
            external_source="tributary",
            external_id="trib_warn_001",
        ),
        agent=admin_agent,
        db=db_session,
    )

    assert result.get("created") is True, f"Expected created=True in warn band, got {result}"
    assert "data" in result
    assert "probable_match" in result
    assert "match_score" in result


# ---------------------------------------------------------------------------
# PATCH auto-inference boundary (sequential on same row)
# ---------------------------------------------------------------------------


def test_patch_auto_inference_sequential(db_session, admin_agent):
    """Phase 1.2 regression: PATCH respects explicit manually_enriched=false,
    then auto-infers true when the field is omitted on subsequent PATCH.
    Tests the boundary on a single row across two PATCHes."""
    # Create a bare row (no description → manually_enriched=False)
    created = _seed(
        db_session, admin_agent,
        description=None,
        date="2026-04-25",
    )
    txn_id = created["data"].id
    assert created["data"].manually_enriched is False

    # PATCH 1: set description with explicit manually_enriched=false
    result1 = transactions.patch_transaction(
        txn_id,
        TransactionUpdate(description="new desc", manually_enriched=False),
        agent=admin_agent,
        db=db_session,
    )
    assert result1["data"].description == "new desc"
    assert result1["data"].manually_enriched is False, \
        "Explicit manually_enriched=false must be respected"

    # PATCH 2: update description WITHOUT manually_enriched → auto-infer True
    result2 = transactions.patch_transaction(
        txn_id,
        TransactionUpdate(description="newer desc"),
        agent=admin_agent,
        db=db_session,
    )
    assert result2["data"].description == "newer desc"
    assert result2["data"].manually_enriched is True, \
        "Omitted manually_enriched should auto-infer True when description is set"


def test_patch_auto_inference_entity_id_only(db_session, admin_agent):
    """Auto-inference also triggers when entity_id is set without
    manually_enriched in the PATCH body."""
    from routers import entities
    from schemas import EntityCreate
    entity = entities.create_entity(
        EntityCreate(scope="salon", name="Test Entity"),
        agent=admin_agent,
        db=db_session,
    )

    created = _seed(db_session, admin_agent, description=None, date="2026-04-26")
    txn_id = created["data"].id
    assert created["data"].manually_enriched is False

    result = transactions.patch_transaction(
        txn_id,
        TransactionUpdate(entity_id=entity["data"].id),
        agent=admin_agent,
        db=db_session,
    )
    assert result["data"].manually_enriched is True
