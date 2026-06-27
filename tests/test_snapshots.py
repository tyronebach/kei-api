import pytest
from fastapi import HTTPException

from routers import snapshots
from schemas import SnapshotCreate


def _create_snapshot(db_session, agent, **overrides):
    payload = {
        "scope": "salon",
        "date": "2026-03-20",
        "data": {"net_worth": 1000},
    }
    payload.update(overrides)
    return snapshots.create_or_update_snapshot(
        SnapshotCreate(**payload),
        agent=agent,
        db=db_session,
    )


def test_snapshot_list_filters_omitted_scope_for_scoped_agent(db_session, admin_agent, salon_agent):
    _create_snapshot(db_session, admin_agent, scope="salon", date="2026-03-20")
    _create_snapshot(db_session, admin_agent, scope="home", date="2026-03-21")

    result = snapshots.list_snapshots(
        scope=None,
        from_date=None,
        to_date=None,
        limit=50,
        offset=0,
        agent=salon_agent,
        db=db_session,
    )

    assert [snap.scope for snap in result] == ["salon"]


def test_snapshot_list_rejects_disallowed_explicit_scope(db_session, admin_agent, salon_agent):
    _create_snapshot(db_session, admin_agent, scope="home")

    with pytest.raises(HTTPException) as exc:
        snapshots.list_snapshots(
            scope="home",
            from_date=None,
            to_date=None,
            limit=50,
            offset=0,
            agent=salon_agent,
            db=db_session,
        )

    assert exc.value.status_code == 403


def test_snapshot_latest_enforces_scope(db_session, admin_agent, salon_agent):
    _create_snapshot(db_session, admin_agent, scope="salon", date="2026-03-20")
    _create_snapshot(db_session, admin_agent, scope="home", date="2026-03-21")

    allowed = snapshots.get_latest_snapshot(
        scope="salon",
        agent=salon_agent,
        db=db_session,
    )
    assert allowed.scope == "salon"

    with pytest.raises(HTTPException) as exc:
        snapshots.get_latest_snapshot(
            scope="home",
            agent=salon_agent,
            db=db_session,
        )

    assert exc.value.status_code == 403


def test_snapshot_get_by_id_enforces_row_scope(db_session, admin_agent, salon_agent):
    salon = _create_snapshot(db_session, admin_agent, scope="salon", date="2026-03-20")
    home = _create_snapshot(db_session, admin_agent, scope="home", date="2026-03-21")

    allowed = snapshots.get_snapshot(salon.id, agent=salon_agent, db=db_session)
    assert allowed.id == salon.id

    with pytest.raises(HTTPException) as exc:
        snapshots.get_snapshot(home.id, agent=salon_agent, db=db_session)

    assert exc.value.status_code == 403


def test_snapshot_post_requires_write_access_to_body_scope(db_session, salon_agent):
    allowed = _create_snapshot(db_session, salon_agent, scope="salon")
    assert allowed.scope == "salon"

    with pytest.raises(HTTPException) as exc:
        _create_snapshot(db_session, salon_agent, scope="home", date="2026-03-21")

    assert exc.value.status_code == 403
