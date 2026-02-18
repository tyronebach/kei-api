from routers import lists
from schemas import ListItemCreate, ListItemUpdate


def _create_list_item(db_session, agent, **overrides):
    payload = {"scope": "home", "list": "shopping", "content": "eggs"}
    payload.update(overrides)
    return lists.create_list_item(
        ListItemCreate(**payload),
        agent=agent,
        db=db_session,
    )["data"]


def test_list_item_position_and_order(db_session, admin_agent):
    first = _create_list_item(db_session, admin_agent, content="eggs")
    second = _create_list_item(db_session, admin_agent, content="milk")

    assert first.position == 1
    assert second.position == 2

    listed = lists.list_items(
        scope="home",
        list="shopping",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    names = [item.content for item in listed["data"]]
    assert names == ["eggs", "milk"]


def test_list_update_and_clear_checked_only(db_session, admin_agent):
    first = _create_list_item(db_session, admin_agent, content="eggs")
    _create_list_item(db_session, admin_agent, content="milk")

    checked = lists.update_list_item(
        first.id,
        ListItemUpdate(checked=True),
        agent=admin_agent,
        db=db_session,
    )
    assert checked["data"].checked is True

    cleared = lists.clear_list(
        scope="home",
        list="shopping",
        checked_only=True,
        agent=admin_agent,
        db=db_session,
    )
    assert cleared["data"]["deleted_count"] == 1

    remaining = lists.list_items(
        scope="home",
        list="shopping",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert remaining["meta"]["total"] == 1
