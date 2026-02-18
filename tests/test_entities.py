import pytest
from fastapi import HTTPException

from routers import entities
from routers import transactions
from schemas import EntityCreate, EntityUpdate, TransactionCreate


def _create_entity(db_session, agent, **overrides):
    payload = {"scope": "salon", "name": "Kevin Lai", "type": "client"}
    payload.update(overrides)
    resp = entities.create_entity(EntityCreate(**payload), agent=agent, db=db_session)
    return resp["data"]


def _create_txn(db_session, agent, **overrides):
    payload = {
        "scope": "salon",
        "type": "income",
        "amount": 75.0,
        "category": "haircut",
        "date": "2026-02-15",
    }
    payload.update(overrides)
    resp = transactions.create_transaction(
        TransactionCreate(**payload),
        agent=agent,
        db=db_session,
    )
    return resp["data"]


def test_entities_crud(db_session, admin_agent):
    created = _create_entity(db_session, admin_agent)
    entity_id = created.id

    listed = entities.list_entities(
        scope="salon",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert listed["meta"]["count"] == 1

    fetched = entities.get_entity(entity_id, agent=admin_agent, db=db_session)
    assert fetched["data"].name == "Kevin Lai"

    updated = entities.update_entity(
        entity_id,
        EntityUpdate(name="Kevin Updated"),
        agent=admin_agent,
        db=db_session,
    )
    assert updated["data"].name == "Kevin Updated"

    deleted = entities.delete_entity(entity_id, agent=admin_agent, db=db_session)
    assert deleted["data"]["deleted"] is True

    with pytest.raises(HTTPException) as exc:
        entities.get_entity(entity_id, agent=admin_agent, db=db_session)
    assert exc.value.status_code == 404


def test_entities_search_meta(db_session, admin_agent):
    _create_entity(db_session, admin_agent, name="Kevin Lai")
    _create_entity(db_session, admin_agent, name="Alice Chen")

    resp = entities.list_entities(
        scope="salon",
        search="keven",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert resp["meta"]["query"] == "keven"
    assert "confident" in resp["meta"]
    assert "best_match" in resp["meta"]
    assert resp["data"]
    assert resp["data"][0].score >= 0.4


def test_entity_activity_and_insights(db_session, admin_agent):
    entity = _create_entity(db_session, admin_agent, name="Repeat Client")
    entity_id = entity.id

    _create_txn(db_session, admin_agent, entity_id=entity_id, amount=50.0, date="2026-02-10")
    _create_txn(db_session, admin_agent, entity_id=entity_id, amount=100.0, date="2026-02-11")
    _create_txn(
        db_session,
        admin_agent,
        entity_id=entity_id,
        type="expense",
        amount=20.0,
        category="supplies",
        date="2026-02-12",
    )

    activity = entities.get_entity_activity(entity_id, agent=admin_agent, db=db_session)
    data = activity["data"]
    assert data["visit_count"] == 2
    assert data["total_spend"] == 150.0
    assert data["avg_spend"] == 75.0

    insights = entities.get_entity_insights(
        scope="salon",
        min_visits=2,
        sort="visits",
        limit=20,
        agent=admin_agent,
        db=db_session,
    )
    ids = {row["id"] for row in insights["data"]}
    assert entity_id in ids
