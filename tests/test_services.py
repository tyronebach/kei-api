from routers import services
from schemas import ServiceCreate, ServiceUpdate


def _create_service(db_session, agent, **overrides):
    payload = {
        "scope": "salon",
        "name": "Haircut",
        "category": "cuts",
        "price": 45.0,
    }
    payload.update(overrides)
    return services.create_service(
        ServiceCreate(**payload),
        agent=agent,
        db=db_session,
    )["data"]


def test_services_crud_and_filters(db_session, admin_agent):
    svc = _create_service(db_session, admin_agent, tags=["regular"])
    _create_service(
        db_session,
        admin_agent,
        name="Balayage",
        category="color",
        price=200.0,
        tags=["premium"],
    )

    listed = services.list_services(
        scope="salon",
        category="cuts",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert listed["meta"]["total"] == 1
    assert listed["data"][0].name == "Haircut"

    tagged = services.list_services(
        scope="salon",
        tag="premium",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert tagged["meta"]["total"] == 1
    assert tagged["data"][0].name == "Balayage"

    updated = services.update_service(
        svc.id,
        ServiceUpdate(price=50.0),
        agent=admin_agent,
        db=db_session,
    )
    assert updated["data"].price == 50.0

    deleted = services.delete_service(svc.id, agent=admin_agent, db=db_session)
    assert deleted["data"]["deleted"] is True
