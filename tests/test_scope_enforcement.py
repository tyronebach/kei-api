import pytest
from fastapi import HTTPException

from routers import entities
from schemas import EntityCreate


def test_scope_filtered_listing(db_session, admin_agent, salon_agent):
    entities.create_entity(
        EntityCreate(scope="salon", name="Salon Client"),
        agent=admin_agent,
        db=db_session,
    )
    entities.create_entity(
        EntityCreate(scope="home", name="Home Person"),
        agent=admin_agent,
        db=db_session,
    )

    listed = entities.list_entities(
        scope=None,
        limit=50,
        offset=0,
        agent=salon_agent,
        db=db_session,
    )
    assert listed["meta"]["total"] == 1
    assert listed["data"][0].scope == "salon"


def test_cross_scope_write_forbidden(db_session, salon_agent):
    with pytest.raises(HTTPException) as exc:
        entities.create_entity(
            EntityCreate(scope="home", name="No Access"),
            agent=salon_agent,
            db=db_session,
        )
    assert exc.value.status_code == 403


def test_read_only_write_forbidden(db_session, read_only_agent):
    with pytest.raises(HTTPException) as exc:
        entities.create_entity(
            EntityCreate(scope="salon", name="Blocked Write"),
            agent=read_only_agent,
            db=db_session,
        )
    assert exc.value.status_code == 403
