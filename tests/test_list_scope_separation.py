"""Tests for Step 5: cross-scope list separation in GET /api/lists."""
from routers import lists
from schemas import ListItemCreate


def _add(db_session, agent, scope, list_name, content):
    return lists.create_list_item(
        ListItemCreate(scope=scope, list=list_name, content=content),
        agent=agent,
        db=db_session,
    )["data"]


def test_same_name_lists_in_different_scopes_are_separate(db_session, admin_agent):
    """Lists with the same name in different scopes must appear as separate entries."""
    _add(db_session, admin_agent, "home", "shopping", "eggs")
    _add(db_session, admin_agent, "home", "shopping", "milk")
    _add(db_session, admin_agent, "salon", "shopping", "shampoo")

    result = lists.get_lists(scope=None, agent=admin_agent, db=db_session)
    data = result["data"]

    assert len(data) == 2, f"Expected 2 (scope, list) combos, got {len(data)}: {data}"

    home_entry = next((r for r in data if r["scope"] == "home" and r["list"] == "shopping"), None)
    salon_entry = next((r for r in data if r["scope"] == "salon" and r["list"] == "shopping"), None)

    assert home_entry is not None
    assert salon_entry is not None
    assert home_entry["total"] == 2
    assert salon_entry["total"] == 1


def test_get_lists_scope_filter_still_works(db_session, admin_agent):
    """Scoped GET /api/lists should only return entries for that scope."""
    _add(db_session, admin_agent, "home", "shopping", "eggs")
    _add(db_session, admin_agent, "salon", "shopping", "shampoo")

    result = lists.get_lists(scope="home", agent=admin_agent, db=db_session)
    data = result["data"]

    assert len(data) == 1
    assert data[0]["scope"] == "home"
    assert data[0]["total"] == 1
