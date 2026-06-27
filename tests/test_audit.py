import pytest
from fastapi import HTTPException

from db.models import Transaction
from routers import audit


def _add_transaction(db_session, **overrides):
    payload = {
        "scope": "salon",
        "type": "expense",
        "amount": 1000,
        "category": "supplies",
        "date": "2026-03-20",
        "description": "duplicate",
    }
    payload.update(overrides)
    txn = Transaction(**payload)
    db_session.add(txn)
    db_session.commit()
    db_session.refresh(txn)
    return txn


def test_audit_stats_apply_scoped_agent_rules(db_session, admin_agent, salon_agent):
    _add_transaction(db_session, scope="salon", date="2026-03-20", description="duplicate")
    _add_transaction(db_session, scope="salon", date="2026-03-20", description="duplicate")
    _add_transaction(db_session, scope="salon", date="2026-03-21", deleted_at=123)
    _add_transaction(db_session, scope="home", date="2026-03-22")
    _add_transaction(db_session, scope="home", date="2026-03-23", deleted_at=123)

    scoped = audit.get_audit_stats(scope=None, agent=salon_agent, db=db_session)
    assert scoped == {
        "soft_deleted_count": 1,
        "content_duplicate_count": 1,
        "active_count": 2,
    }

    explicit = audit.get_audit_stats(scope="salon", agent=salon_agent, db=db_session)
    assert explicit == scoped

    all_scopes = audit.get_audit_stats(scope=None, agent=admin_agent, db=db_session)
    assert all_scopes == {
        "soft_deleted_count": 2,
        "content_duplicate_count": 1,
        "active_count": 3,
    }


def test_audit_stats_reject_disallowed_explicit_scope(db_session, salon_agent):
    with pytest.raises(HTTPException) as exc:
        audit.get_audit_stats(scope="home", agent=salon_agent, db=db_session)

    assert exc.value.status_code == 403


def test_purge_soft_deleted_requires_wildcard_write(db_session, admin_agent, salon_agent):
    _add_transaction(db_session, scope="salon", deleted_at=123)

    with pytest.raises(HTTPException) as exc:
        audit.purge_soft_deleted(agent=salon_agent, db=db_session)

    assert exc.value.status_code == 403
    assert db_session.query(Transaction).filter(Transaction.deleted_at.isnot(None)).count() == 1

    result = audit.purge_soft_deleted(agent=admin_agent, db=db_session)
    assert result == {"deleted_count": 1}
    assert db_session.query(Transaction).filter(Transaction.deleted_at.isnot(None)).count() == 0
