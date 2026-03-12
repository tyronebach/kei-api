"""Tests for Step 4: same-scope entity reference integrity."""
import pytest
from fastapi import HTTPException

from routers import entities, transactions
from schemas import EntityCreate, TransactionCreate, TransactionUpdate


def _create_entity(db_session, agent, scope="salon"):
    return entities.create_entity(
        EntityCreate(scope=scope, name="Test Client"),
        agent=agent,
        db=db_session,
    )["data"]


def _create_txn(db_session, agent, **overrides):
    payload = {
        "scope": "salon",
        "type": "income",
        "amount": 80.0,
        "category": "haircut",
        "date": "2026-03-12",
    }
    payload.update(overrides)
    return transactions.create_transaction(
        TransactionCreate(**payload),
        agent=agent,
        db=db_session,
    )["data"]


def test_same_scope_entity_accepted(db_session, admin_agent):
    entity = _create_entity(db_session, admin_agent, scope="salon")
    txn = _create_txn(db_session, admin_agent, scope="salon", entity_id=entity.id)
    assert txn.entity_id == entity.id


def test_cross_scope_entity_rejected_on_create(db_session, admin_agent):
    """Entity in 'home' scope cannot be referenced from 'salon' transaction."""
    entity = _create_entity(db_session, admin_agent, scope="home")

    with pytest.raises(HTTPException) as exc_info:
        _create_txn(db_session, admin_agent, scope="salon", entity_id=entity.id)
    assert exc_info.value.status_code == 422


def test_cross_scope_entity_rejected_on_update(db_session, admin_agent):
    """Updating a transaction to reference an entity in a different scope is rejected."""
    home_entity = _create_entity(db_session, admin_agent, scope="home")
    txn = _create_txn(db_session, admin_agent, scope="salon")

    with pytest.raises(HTTPException) as exc_info:
        transactions.update_transaction(
            txn.id,
            TransactionUpdate(entity_id=home_entity.id),
            agent=admin_agent,
            db=db_session,
        )
    assert exc_info.value.status_code == 422


def test_missing_entity_rejected(db_session, admin_agent):
    """Referencing a non-existent entity_id is rejected with 422."""
    with pytest.raises(HTTPException) as exc_info:
        _create_txn(db_session, admin_agent, entity_id="nonexistent-id")
    assert exc_info.value.status_code == 422
