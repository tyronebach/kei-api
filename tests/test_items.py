import pytest
from fastapi import HTTPException

from routers import items
from schemas import ItemAdjust, ItemCreate, ItemUpdate


def _create_item(db_session, agent, **overrides):
    payload = {
        "scope": "salon",
        "name": "Purple Shampoo",
        "quantity": 10.0,
        "unit": "bottle",
        "reorder_threshold": 3.0,
    }
    payload.update(overrides)
    return items.create_item(ItemCreate(**payload), agent=agent, db=db_session)["data"]


def test_items_crud_and_search(db_session, admin_agent):
    item = _create_item(db_session, admin_agent)
    item_id = item.id

    fetched = items.get_item(item_id, agent=admin_agent, db=db_session)
    assert fetched["data"].name == "Purple Shampoo"

    searched = items.list_items(
        scope="salon",
        search="purpel",
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert searched["meta"]["query"] == "purpel"
    assert searched["data"]

    updated = items.update_item(
        item_id,
        ItemUpdate(quantity=7.0),
        agent=admin_agent,
        db=db_session,
    )
    assert updated["data"].quantity == 7.0

    deleted = items.delete_item(item_id, agent=admin_agent, db=db_session)
    assert deleted["data"]["deleted"] is True


def test_item_adjust_and_movement_history(db_session, admin_agent):
    item = _create_item(db_session, admin_agent, quantity=10.0)
    item_id = item.id

    inc = items.adjust_item(
        item_id,
        ItemAdjust(type="in", quantity=5.0, reason="restock"),
        agent=admin_agent,
        db=db_session,
    )
    assert inc["data"].quantity == 15.0

    dec = items.adjust_item(
        item_id,
        ItemAdjust(type="out", quantity=3.0, reason="used"),
        agent=admin_agent,
        db=db_session,
    )
    assert dec["data"].quantity == 12.0

    set_qty = items.adjust_item(
        item_id,
        ItemAdjust(type="adjustment", quantity=8.0, reason="counted"),
        agent=admin_agent,
        db=db_session,
    )
    assert set_qty["data"].quantity == 8.0

    with pytest.raises(HTTPException) as exc:
        items.adjust_item(
            item_id,
            ItemAdjust(type="out", quantity=100.0),
            agent=admin_agent,
            db=db_session,
        )
    assert exc.value.status_code == 409

    movements = items.list_item_movements(
        item_id,
        limit=50,
        offset=0,
        agent=admin_agent,
        db=db_session,
    )
    assert movements["meta"]["total"] == 3


def test_low_stock_filter(db_session, admin_agent):
    low_item = _create_item(
        db_session,
        admin_agent,
        name="Foil Sheets",
        quantity=2.0,
        reorder_threshold=5.0,
    )
    _create_item(
        db_session,
        admin_agent,
        name="Gloves",
        quantity=10.0,
        reorder_threshold=5.0,
    )

    resp = items.list_low_stock(scope="salon", agent=admin_agent, db=db_session)
    ids = {item.id for item in resp["data"]}
    assert low_item.id in ids
