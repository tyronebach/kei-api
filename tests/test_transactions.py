import pytest
from fastapi import HTTPException

from routers import transactions
from schemas import TransactionCreate, TransactionUpdate


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
