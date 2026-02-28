"""Tests for recurring income/expense rules."""

from datetime import date

import pytest
from fastapi import HTTPException

from routers import recurring
from schemas import RecurringRuleCreate, RecurringRuleUpdate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(db_session, agent, **overrides):
    payload = {
        "scope": "home",
        "name": "Rent",
        "type": "expense",
        "amount": 2000.0,
        "category": "housing",
        "frequency": "monthly",
        "day_of_month": 1,
        "start_date": "2026-01-01",
    }
    payload.update(overrides)
    return recurring.create_rule(
        RecurringRuleCreate(**payload),
        agent=agent,
        db=db_session,
    )["data"]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def test_create_and_get(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent)
    assert rule.name == "Rent"
    assert rule.amount == 2000.0
    assert rule.frequency == "monthly"
    # next_due is on or after today — just verify it's a valid date string
    assert rule.next_due is not None
    assert rule.next_due >= date.today().isoformat()

    fetched = recurring.get_rule(rule.id, agent=admin_agent, db=db_session)["data"]
    assert fetched.id == rule.id


def test_list_rules(db_session, admin_agent):
    _make_rule(db_session, admin_agent, name="Rent", category="housing")
    _make_rule(db_session, admin_agent, name="Netflix", type="expense", category="subscriptions",
               frequency="monthly", amount=20.0)
    _make_rule(db_session, admin_agent, name="Salary", type="income", category="salary",
               frequency="monthly", amount=5000.0)

    result = recurring.list_rules(scope="home", type=None, category=None,
                                  active_only=True, limit=50, offset=0,
                                  agent=admin_agent, db=db_session)
    assert result["meta"]["total"] == 3

    expenses = recurring.list_rules(scope="home", type="expense", category=None,
                                    active_only=True, limit=50, offset=0,
                                    agent=admin_agent, db=db_session)
    assert expenses["meta"]["total"] == 2


def test_update_inplace(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent)
    updated = recurring.update_rule(
        rule.id,
        RecurringRuleUpdate(amount=2200.0, name="Rent (raised)"),
        effective_from=None,
        agent=admin_agent,
        db=db_session,
    )["data"]
    assert updated.amount == 2200.0
    assert updated.name == "Rent (raised)"


def test_update_with_fork(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent)
    result = recurring.update_rule(
        rule.id,
        RecurringRuleUpdate(amount=2500.0),
        effective_from="2026-04-01",
        agent=admin_agent,
        db=db_session,
    )
    new_rule = result["data"]
    assert result["forked_from"] == rule.id
    assert new_rule.amount == 2500.0
    assert new_rule.start_date == "2026-04-01"
    assert new_rule.end_date is None  # no end on the fork

    # Old rule should now end on 2026-03-31
    old = recurring.get_rule(rule.id, agent=admin_agent, db=db_session)["data"]
    assert old.end_date == "2026-03-31"


def test_stop(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent)
    # Stop in the past → next_due should be None
    stopped = recurring.stop_rule(rule.id, end_date="2026-01-31",
                                  agent=admin_agent, db=db_session)["data"]
    assert stopped.end_date == "2026-01-31"
    assert stopped.next_due is None


def test_delete(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent)
    recurring.delete_rule(rule.id, agent=admin_agent, db=db_session)
    with pytest.raises(HTTPException) as exc:
        recurring.get_rule(rule.id, agent=admin_agent, db=db_session)
    assert exc.value.status_code == 404


def test_read_only_cannot_create(db_session, read_only_agent):
    with pytest.raises(HTTPException) as exc:
        _make_rule(db_session, read_only_agent)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Instances (lazy generation)
# ---------------------------------------------------------------------------

def test_monthly_instances(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent, start_date="2026-01-01", day_of_month=1)
    result = recurring.get_instances(
        rule.id, from_date="2026-01-01", to_date="2026-06-30",
        agent=admin_agent, db=db_session,
    )
    instances = result["data"]
    assert len(instances) == 6
    assert all(i.status == "projected" for i in instances)
    dates = [i.rule_date for i in instances]
    assert dates == ["2026-01-01", "2026-02-01", "2026-03-01",
                     "2026-04-01", "2026-05-01", "2026-06-01"]


def test_weekly_instances(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent, frequency="weekly",
                      start_date="2026-01-05", day_of_month=None)
    result = recurring.get_instances(
        rule.id, from_date="2026-01-05", to_date="2026-01-26",
        agent=admin_agent, db=db_session,
    )
    assert len(result["data"]) == 4


def test_yearly_instances(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent, frequency="yearly",
                      start_date="2026-03-15", day_of_month=None,
                      name="Annual insurance")
    result = recurring.get_instances(
        rule.id, from_date="2026-01-01", to_date="2028-12-31",
        agent=admin_agent, db=db_session,
    )
    assert len(result["data"]) == 3
    assert result["data"][0].rule_date == "2026-03-15"
    assert result["data"][1].rule_date == "2027-03-15"


def test_instances_respect_end_date(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent,
                      start_date="2026-01-01", end_date="2026-03-31")
    result = recurring.get_instances(
        rule.id, from_date="2026-01-01", to_date="2026-06-30",
        agent=admin_agent, db=db_session,
    )
    assert len(result["data"]) == 3  # Jan, Feb, Mar only


# ---------------------------------------------------------------------------
# Skip / unskip
# ---------------------------------------------------------------------------

def test_skip_and_restore(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent, start_date="2026-01-01")

    recurring.skip_occurrence(rule.id, skip_date="2026-02-01",
                              agent=admin_agent, db=db_session)

    result = recurring.get_instances(
        rule.id, from_date="2026-01-01", to_date="2026-03-31",
        agent=admin_agent, db=db_session,
    )
    statuses = {i.rule_date: i.status for i in result["data"]}
    assert statuses["2026-01-01"] == "projected"
    assert statuses["2026-02-01"] == "skipped"
    assert statuses["2026-03-01"] == "projected"

    recurring.unskip_occurrence(rule.id, skip_date="2026-02-01",
                                agent=admin_agent, db=db_session)
    result2 = recurring.get_instances(
        rule.id, from_date="2026-02-01", to_date="2026-02-28",
        agent=admin_agent, db=db_session,
    )
    assert result2["data"][0].status == "projected"


def test_skip_idempotent(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent)
    recurring.skip_occurrence(rule.id, skip_date="2026-03-01",
                              agent=admin_agent, db=db_session)
    result = recurring.skip_occurrence(rule.id, skip_date="2026-03-01",
                                       agent=admin_agent, db=db_session)
    assert result["data"]["status"] == "already_skipped"


# ---------------------------------------------------------------------------
# Materialise
# ---------------------------------------------------------------------------

def test_generate_creates_transactions(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent, start_date="2026-01-01")

    result = recurring.generate_instances(
        rule.id, through="2026-03-31", agent=admin_agent, db=db_session,
    )
    assert result["data"]["created"] == 3
    assert "2026-01-01" in result["data"]["dates"]

    # Calling again is idempotent — no duplicates
    result2 = recurring.generate_instances(
        rule.id, through="2026-03-31", agent=admin_agent, db=db_session,
    )
    assert result2["data"]["created"] == 0

    # Instances now show as confirmed
    instances = recurring.get_instances(
        rule.id, from_date="2026-01-01", to_date="2026-03-31",
        agent=admin_agent, db=db_session,
    )["data"]
    assert all(i.status == "confirmed" for i in instances)


def test_generate_skips_skipped_dates(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent, start_date="2026-01-01")
    recurring.skip_occurrence(rule.id, skip_date="2026-02-01",
                              agent=admin_agent, db=db_session)

    result = recurring.generate_instances(
        rule.id, through="2026-03-31", agent=admin_agent, db=db_session,
    )
    assert result["data"]["created"] == 2
    assert "2026-02-01" not in result["data"]["dates"]


# ---------------------------------------------------------------------------
# Settle
# ---------------------------------------------------------------------------

def test_settle_materialises_past_due(db_session, admin_agent):
    # Rule starting in the past → occurrences up to today should be settled
    _make_rule(db_session, admin_agent, start_date="2026-01-01", name="Rent")
    _make_rule(db_session, admin_agent, name="Netflix", amount=20.0,
               category="bills", start_date="2026-01-01", day_of_month=None)

    result = recurring.settle_due(scope="home", agent=admin_agent, db=db_session)
    data = result["data"]
    assert data["total_created"] > 0
    assert data["rules_settled"] == 2


def test_settle_is_idempotent(db_session, admin_agent):
    _make_rule(db_session, admin_agent, start_date="2026-01-01")

    first = recurring.settle_due(scope="home", agent=admin_agent, db=db_session)
    created_first = first["data"]["total_created"]
    assert created_first > 0

    second = recurring.settle_due(scope="home", agent=admin_agent, db=db_session)
    assert second["data"]["total_created"] == 0


def test_settle_skips_skipped_dates(db_session, admin_agent):
    rule = _make_rule(db_session, admin_agent, start_date="2026-01-01")
    recurring.skip_occurrence(rule.id, skip_date="2026-01-01",
                              agent=admin_agent, db=db_session)

    result = recurring.settle_due(scope="home", agent=admin_agent, db=db_session)
    # Jan 1 should not be created
    for entry in result["data"]["settled"]:
        if entry["rule_id"] == rule.id:
            assert "2026-01-01" not in entry["dates"]


def test_settle_read_only_denied(db_session, read_only_agent):
    with pytest.raises(HTTPException) as exc:
        recurring.settle_due(scope="home", agent=read_only_agent, db=db_session)
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Scope enforcement
# ---------------------------------------------------------------------------

def test_scope_isolation(db_session, salon_agent, admin_agent):
    home_rule = _make_rule(db_session, admin_agent, scope="home")
    with pytest.raises(HTTPException) as exc:
        recurring.get_rule(home_rule.id, agent=salon_agent, db=db_session)
    assert exc.value.status_code == 403
