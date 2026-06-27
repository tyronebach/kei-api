import pytest
from fastapi import HTTPException

from db.models import Transaction
from routers import audit, items, snapshots, transactions
from schemas import ItemAdjust, ItemCreate, SnapshotCreate, TransactionCreate


def _create_snapshot(db_session, agent, **overrides):
    payload = {
        "scope": "salon",
        "date": "2026-03-20",
        "data": {"net_worth": {"net": 1000}},
    }
    payload.update(overrides)
    return snapshots.create_or_update_snapshot(
        SnapshotCreate(**payload),
        agent=agent,
        db=db_session,
    )


def _create_transaction(db_session, agent, **overrides):
    payload = {
        "scope": "salon",
        "type": "expense",
        "amount": 20.0,
        "category": "supplies",
        "date": "2026-03-20",
        "force_create": True,
    }
    payload.update(overrides)
    return transactions.create_transaction(
        TransactionCreate(**payload),
        agent=agent,
        db=db_session,
    )["data"]


def test_migrated_schema_snapshot_scope_enforcement(
    migrated_db_session,
    admin_agent,
    salon_agent,
):
    salon = _create_snapshot(
        migrated_db_session,
        admin_agent,
        scope="salon",
        date="2026-03-20",
    )
    home = _create_snapshot(
        migrated_db_session,
        admin_agent,
        scope="home",
        date="2026-03-21",
    )

    listed = snapshots.list_snapshots(
        scope=None,
        from_date=None,
        to_date=None,
        limit=50,
        offset=0,
        agent=salon_agent,
        db=migrated_db_session,
    )
    assert [snap.id for snap in listed] == [salon.id]

    with pytest.raises(HTTPException) as exc:
        snapshots.get_snapshot(home.id, agent=salon_agent, db=migrated_db_session)
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        _create_snapshot(
            migrated_db_session,
            salon_agent,
            scope="home",
            date="2026-03-22",
        )
    assert exc.value.status_code == 403


def test_migrated_schema_audit_scope_and_purge_rules(
    migrated_db_session,
    admin_agent,
    salon_agent,
):
    migrated_db_session.add_all(
        [
            Transaction(
                scope="salon",
                type="expense",
                amount=1000,
                category="supplies",
                date="2026-03-20",
                description="duplicate",
            ),
            Transaction(
                scope="salon",
                type="expense",
                amount=1000,
                category="supplies",
                date="2026-03-20",
                description="duplicate",
            ),
            Transaction(
                scope="home",
                type="expense",
                amount=1000,
                category="supplies",
                date="2026-03-20",
                deleted_at=123,
            ),
        ]
    )
    migrated_db_session.commit()

    scoped = audit.get_audit_stats(
        scope=None,
        agent=salon_agent,
        db=migrated_db_session,
    )
    assert scoped == {
        "soft_deleted_count": 0,
        "content_duplicate_count": 1,
        "active_count": 2,
    }

    with pytest.raises(HTTPException) as exc:
        audit.purge_soft_deleted(agent=salon_agent, db=migrated_db_session)
    assert exc.value.status_code == 403

    result = audit.purge_soft_deleted(agent=admin_agent, db=migrated_db_session)
    assert result == {"deleted_count": 1}


def test_migrated_schema_external_identity_scope_collision(
    migrated_db_session,
    admin_agent,
):
    _create_transaction(
        migrated_db_session,
        admin_agent,
        scope="home",
        external_source="tributary",
        external_id="collision-1",
    )

    with pytest.raises(HTTPException) as exc:
        _create_transaction(
            migrated_db_session,
            admin_agent,
            scope="salon",
            external_source="tributary",
            external_id="collision-1",
        )

    assert exc.value.status_code == 409


def test_migrated_schema_item_movement_rejects_cross_scope_transaction(
    migrated_db_session,
    admin_agent,
):
    item = items.create_item(
        ItemCreate(scope="salon", name="Foil", quantity=5.0),
        agent=admin_agent,
        db=migrated_db_session,
    )["data"]
    txn = _create_transaction(
        migrated_db_session,
        admin_agent,
        scope="home",
        date="2026-03-21",
    )

    with pytest.raises(HTTPException) as exc:
        items.adjust_item(
            item.id,
            ItemAdjust(type="adjustment", quantity=4.0, transaction_id=txn.id),
            agent=admin_agent,
            db=migrated_db_session,
        )

    assert exc.value.status_code == 422
