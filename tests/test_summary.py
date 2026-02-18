from datetime import date

from routers import entities, items, summary, transactions
from schemas import EntityCreate, ItemCreate, TransactionCreate


def _create_entity(db_session, agent):
    return entities.create_entity(
        EntityCreate(scope="salon", name="Client One", type="client"),
        agent=agent,
        db=db_session,
    )["data"]


def _create_item(db_session, agent):
    return items.create_item(
        ItemCreate(
            scope="salon",
            name="Foil",
            quantity=2.0,
            reorder_threshold=5.0,
        ),
        agent=agent,
        db=db_session,
    )["data"]


def _create_txn(db_session, agent, **overrides):
    today = date.today().isoformat()
    payload = {
        "scope": "salon",
        "type": "income",
        "amount": 100.0,
        "category": "haircut",
        "date": today,
    }
    payload.update(overrides)
    return transactions.create_transaction(
        TransactionCreate(**payload),
        agent=agent,
        db=db_session,
    )["data"]


def test_summary_custom_period(db_session, admin_agent):
    today = date.today().isoformat()
    entity = _create_entity(db_session, admin_agent)
    _create_item(db_session, admin_agent)
    _create_txn(db_session, admin_agent, entity_id=entity.id, amount=100.0)
    _create_txn(
        db_session,
        admin_agent,
        type="expense",
        amount=40.0,
        category="supplies",
    )

    resp = summary.get_summary(
        scope="salon",
        period="custom",
        from_date=today,
        to_date=today,
        agent=admin_agent,
        db=db_session,
    )
    data = resp["data"]
    assert data["income"]["total"] == 100.0
    assert data["expenses"]["total"] == 40.0
    assert data["profit"] == 60.0
    assert data["clients"]["active"] == 1
    assert data["inventory_alerts"] == 1


def test_summary_trends_empty_db(db_session, admin_agent):
    today = date.today().isoformat()
    resp = summary.get_trends(
        scope="salon",
        period="custom",
        from_date=today,
        to_date=today,
        agent=admin_agent,
        db=db_session,
    )
    data = resp["data"]
    assert data["current"]["income"] == 0.0
    assert data["current"]["expenses"] == 0.0
    assert data["trend"] == "stable"


def test_summary_by_day(db_session, admin_agent):
    today = date.today().isoformat()
    _create_txn(db_session, admin_agent, amount=123.0)

    resp = summary.get_by_day(
        scope="salon",
        period="custom",
        from_date=today,
        to_date=today,
        agent=admin_agent,
        db=db_session,
    )
    data = resp["data"]
    assert len(data["days"]) == 7
    total = round(sum(day["total"] for day in data["days"]), 2)
    assert total == 123.0
    assert data["busiest"] in {day["day"] for day in data["days"]}


def test_summary_by_scope(db_session, admin_agent):
    today = date.today().isoformat()
    _create_txn(db_session, admin_agent, scope="salon", amount=200.0)
    _create_txn(
        db_session,
        admin_agent,
        scope="salon",
        type="expense",
        amount=50.0,
        category="supplies",
    )
    _create_txn(db_session, admin_agent, scope="home", amount=80.0)

    resp = summary.get_summary_by_scope(
        period="custom",
        from_date=today,
        to_date=today,
        agent=admin_agent,
        db=db_session,
    )
    assert resp["meta"]["count"] == 2
    scopes = {row["scope"]: row for row in resp["data"]["scopes"]}
    assert scopes["salon"]["profit"] == 150.0
    assert scopes["home"]["income"]["total"] == 80.0
