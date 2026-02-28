"""Recurring income/expense rules.

Design: template (RecurringRule) + instances (Transaction rows with rule_id).
Instances are generated lazily on read — no background job required.
"""

from __future__ import annotations

import calendar
import time
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from db.connection import get_db
from db.helpers import active_query, apply_scope_filter, get_scoped_or_404
from db.models import RecurringRule, RecurringSkip, Transaction
from dependencies import AgentPrincipal, get_current_agent, validate_scope
from schemas import (
    RecurringInstanceOut,
    RecurringRuleCreate,
    RecurringRuleOut,
    RecurringRuleUpdate,
    TransactionOut,
)

router = APIRouter(prefix="/api/recurring", tags=["recurring"])

_MAX_GENERATE_DAYS = 366 * 3  # safety cap for materialise endpoint


# ---------------------------------------------------------------------------
# Date arithmetic helpers
# ---------------------------------------------------------------------------

def _add_months(d: date, n: int) -> date:
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _next_occurrence(current: date, rule: RecurringRule) -> date:
    freq = rule.frequency
    if freq == "monthly":
        nxt = _add_months(current, rule.interval)
        # Snap to day_of_month if set (capped at month length)
        if rule.day_of_month:
            _, last = calendar.monthrange(nxt.year, nxt.month)
            nxt = nxt.replace(day=min(rule.day_of_month, last))
        return nxt
    if freq == "weekly":
        return current + timedelta(weeks=rule.interval)
    if freq == "biweekly":
        return current + timedelta(weeks=2 * rule.interval)
    if freq == "yearly":
        try:
            return current.replace(year=current.year + rule.interval)
        except ValueError:
            # Feb 29 → Feb 28
            return current.replace(year=current.year + rule.interval, day=28)
    # custom: interval = number of days
    return current + timedelta(days=rule.interval)


def _first_occurrence(rule: RecurringRule) -> date:
    """Return the first occurrence on or after start_date, honouring day_of_month."""
    d = date.fromisoformat(rule.start_date)
    if rule.frequency == "monthly" and rule.day_of_month:
        _, last = calendar.monthrange(d.year, d.month)
        target_day = min(rule.day_of_month, last)
        if d.day <= target_day:
            d = d.replace(day=target_day)
        else:
            # Roll to next month
            d = _add_months(d, 1)
            _, last = calendar.monthrange(d.year, d.month)
            d = d.replace(day=min(rule.day_of_month, last))
    return d


def _occurrences_in_range(rule: RecurringRule, from_date: date, to_date: date) -> list[date]:
    """All canonical occurrence dates for a rule within [from_date, to_date]."""
    end = date.fromisoformat(rule.end_date) if rule.end_date else None
    results: list[date] = []
    current = _first_occurrence(rule)

    # Fast-forward to range start
    while current < from_date:
        nxt = _next_occurrence(current, rule)
        if nxt <= current:
            break  # safety: prevent infinite loop on bad data
        current = nxt

    while current <= to_date:
        if end and current > end:
            break
        results.append(current)
        nxt = _next_occurrence(current, rule)
        if nxt <= current:
            break
        current = nxt

    return results


def _next_due(rule: RecurringRule) -> str | None:
    """Next occurrence on or after today (for list view)."""
    today = date.today()
    end = date.fromisoformat(rule.end_date) if rule.end_date else None
    if end and end < today:
        return None
    current = _first_occurrence(rule)
    while current < today:
        nxt = _next_occurrence(current, rule)
        if nxt <= current:
            return None
        current = nxt
    if end and current > end:
        return None
    return current.isoformat()


def _rule_to_out(rule: RecurringRule) -> RecurringRuleOut:
    data = RecurringRuleOut.model_validate(rule)
    data.next_due = _next_due(rule)
    return data


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
def create_rule(
    body: RecurringRuleCreate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Create a recurring income or expense rule."""
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")
    validate_scope(body.scope)
    if not agent.can_access_scope(body.scope):
        raise HTTPException(status_code=403, detail=f"No write access to scope '{body.scope}'")

    rule = RecurringRule(**body.model_dump(exclude_none=True), created_by=agent.agent_id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"data": _rule_to_out(rule)}


@router.get("")
def list_rules(
    scope: str | None = None,
    type: str | None = None,
    category: str | None = None,
    active_only: bool = Query(True, description="Exclude rules whose end_date has passed"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """List recurring rules, optionally filtered by scope / type / category."""
    q = apply_scope_filter(active_query(db, RecurringRule), RecurringRule, scope, agent)
    if type:
        q = q.filter(RecurringRule.type == type)
    if category:
        cats = [c.strip() for c in category.split(",")]
        q = q.filter(RecurringRule.category.in_(cats))
    if active_only:
        today = date.today().isoformat()
        q = q.filter(
            (RecurringRule.end_date.is_(None)) | (RecurringRule.end_date >= today)
        )

    total = q.count()
    rules = q.order_by(RecurringRule.name.asc()).offset(offset).limit(limit).all()
    return {
        "data": [_rule_to_out(r) for r in rules],
        "meta": {"count": len(rules), "total": total},
    }


@router.get("/{rule_id}")
def get_rule(
    rule_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    rule = get_scoped_or_404(db, RecurringRule, rule_id, agent)
    return {"data": _rule_to_out(rule)}


@router.patch("/{rule_id}")
def update_rule(
    rule_id: str,
    body: RecurringRuleUpdate,
    effective_from: str | None = Query(
        None,
        description=(
            "If set (YYYY-MM-DD), close this rule on effective_from-1 and fork a new rule "
            "from effective_from with the updates applied. Use for 'change going forward'."
        ),
    ),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """
    Update a recurring rule.

    - Without effective_from: edits the rule in place (affects all unmodified future instances).
    - With effective_from: closes the current rule and creates a forked rule from that date.
      Use this for 'change rent to $1500 from March 1st'.
    """
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    rule = get_scoped_or_404(db, RecurringRule, rule_id, agent)
    updates = body.model_dump(exclude_unset=True)

    if effective_from:
        try:
            fork_date = date.fromisoformat(effective_from)
        except ValueError:
            raise HTTPException(status_code=422, detail="effective_from must be YYYY-MM-DD")

        # Capture original end_date BEFORE we close the old rule
        original_end_date = rule.end_date

        # Close the current rule one day before fork date
        close_date = (fork_date - timedelta(days=1)).isoformat()
        # Don't extend beyond existing end_date
        if rule.end_date and rule.end_date < close_date:
            close_date = rule.end_date
        rule.end_date = close_date
        rule.updated_by = agent.agent_id

        # Fork: copy current rule, apply updates, start from fork_date
        fork_data = {
            "scope": rule.scope,
            "name": updates.get("name", rule.name),
            "type": rule.type,
            "amount": updates.get("amount", rule.amount),
            "category": updates.get("category", rule.category),
            "frequency": updates.get("frequency", rule.frequency),
            "interval": updates.get("interval", rule.interval),
            "day_of_month": updates.get("day_of_month", rule.day_of_month),
            "start_date": effective_from,
            "end_date": updates.get("end_date", original_end_date),  # original end survives
            "description": updates.get("description", rule.description),
            "entity_id": updates.get("entity_id", rule.entity_id),
            "payment_method": updates.get("payment_method", rule.payment_method),
            "tags": updates.get("tags", rule.tags),
            "meta": updates.get("meta", rule.meta),
            "created_by": agent.agent_id,
        }
        new_rule = RecurringRule(**{k: v for k, v in fork_data.items() if v is not None})
        db.add(new_rule)
        db.commit()
        db.refresh(new_rule)
        return {"data": _rule_to_out(new_rule), "forked_from": rule_id}

    # In-place update
    for key, value in updates.items():
        setattr(rule, key, value)
    rule.updated_by = agent.agent_id
    db.commit()
    db.refresh(rule)
    return {"data": _rule_to_out(rule)}


@router.post("/{rule_id}/stop")
def stop_rule(
    rule_id: str,
    end_date: str | None = Query(None, description="Stop date (YYYY-MM-DD). Defaults to today."),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Stop a recurring rule by setting its end_date."""
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    rule = get_scoped_or_404(db, RecurringRule, rule_id, agent)
    stop = end_date or date.today().isoformat()
    try:
        date.fromisoformat(stop)
    except ValueError:
        raise HTTPException(status_code=422, detail="end_date must be YYYY-MM-DD")

    rule.end_date = stop
    rule.updated_by = agent.agent_id
    db.commit()
    db.refresh(rule)
    return {"data": _rule_to_out(rule)}


@router.post("/{rule_id}/skip")
def skip_occurrence(
    rule_id: str,
    skip_date: str = Query(..., description="Date to skip (YYYY-MM-DD)"),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Mark one occurrence of a recurring rule as skipped."""
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    rule = get_scoped_or_404(db, RecurringRule, rule_id, agent)
    try:
        date.fromisoformat(skip_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="skip_date must be YYYY-MM-DD")

    existing = (
        db.query(RecurringSkip)
        .filter(RecurringSkip.rule_id == rule_id, RecurringSkip.skip_date == skip_date)
        .first()
    )
    if existing:
        return {"data": {"rule_id": rule_id, "skip_date": skip_date, "status": "already_skipped"}}

    skip = RecurringSkip(rule_id=rule_id, skip_date=skip_date)
    db.add(skip)
    db.commit()
    return {"data": {"rule_id": rule_id, "skip_date": skip_date, "status": "skipped"}}


@router.delete("/{rule_id}/skip/{skip_date}")
def unskip_occurrence(
    rule_id: str,
    skip_date: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Remove a skip — restores the occurrence as projected."""
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    get_scoped_or_404(db, RecurringRule, rule_id, agent)
    skip = (
        db.query(RecurringSkip)
        .filter(RecurringSkip.rule_id == rule_id, RecurringSkip.skip_date == skip_date)
        .first()
    )
    if not skip:
        raise HTTPException(status_code=404, detail="Skip not found")
    db.delete(skip)
    db.commit()
    return {"data": {"rule_id": rule_id, "skip_date": skip_date, "status": "restored"}}


# ---------------------------------------------------------------------------
# Instances (lazy read) + materialise (write)
# ---------------------------------------------------------------------------

@router.get("/{rule_id}/instances")
def get_instances(
    rule_id: str,
    from_date: str = Query(..., alias="from", description="Start date YYYY-MM-DD"),
    to_date: str = Query(..., alias="to", description="End date YYYY-MM-DD"),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """
    Return all occurrences of a rule within a date range.

    Each instance is one of:
    - projected  — no transaction row yet (future or unconfirmed)
    - confirmed  — a materialised transaction row exists
    - skipped    — manually skipped via /skip
    """
    rule = get_scoped_or_404(db, RecurringRule, rule_id, agent)
    try:
        f = date.fromisoformat(from_date)
        t = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="from/to must be YYYY-MM-DD")
    if f > t:
        raise HTTPException(status_code=422, detail="from must be <= to")

    occurrences = _occurrences_in_range(rule, f, t)

    # Load actual transactions linked to this rule in range
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.rule_id == rule_id,
            Transaction.rule_date >= from_date,
            Transaction.rule_date <= to_date,
            Transaction.deleted_at.is_(None),
        )
        .all()
    )
    txn_by_rule_date: dict[str, Transaction] = {t.rule_date: t for t in txns if t.rule_date}

    # Load skips
    skips = (
        db.query(RecurringSkip)
        .filter(
            RecurringSkip.rule_id == rule_id,
            RecurringSkip.skip_date >= from_date,
            RecurringSkip.skip_date <= to_date,
        )
        .all()
    )
    skipped_dates = {s.skip_date for s in skips}

    results: list[RecurringInstanceOut] = []
    for occ in occurrences:
        occ_str = occ.isoformat()
        if occ_str in skipped_dates:
            status = "skipped"
            txn = None
        elif occ_str in txn_by_rule_date:
            status = "confirmed"
            txn = txn_by_rule_date[occ_str]
        else:
            status = "projected"
            txn = None

        results.append(RecurringInstanceOut(
            rule_id=rule_id,
            rule_date=occ_str,
            status=status,
            transaction_id=txn.id if txn else None,
            amount=txn.amount if txn else rule.amount,
            type=txn.type if txn else rule.type,
            category=txn.category if txn else rule.category,
            date=txn.date if txn else occ_str,
            description=txn.description if txn else rule.description,
            entity_id=txn.entity_id if txn else rule.entity_id,
            payment_method=txn.payment_method if txn else rule.payment_method,
        ))

    return {"data": results, "meta": {"count": len(results)}}


@router.post("/{rule_id}/generate")
def generate_instances(
    rule_id: str,
    through: str = Query(..., description="Materialise up to this date (YYYY-MM-DD)"),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """
    Materialise projected occurrences as real transaction rows up to `through` date.
    Already-confirmed and skipped occurrences are left untouched.
    Returns a summary of created rows.
    """
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    rule = get_scoped_or_404(db, RecurringRule, rule_id, agent)
    try:
        end = date.fromisoformat(through)
    except ValueError:
        raise HTTPException(status_code=422, detail="through must be YYYY-MM-DD")

    today = date.today()
    start = date.fromisoformat(rule.start_date)
    if (end - start).days > _MAX_GENERATE_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Range too large — max {_MAX_GENERATE_DAYS} days",
        )

    occurrences = _occurrences_in_range(rule, start, end)

    # Existing transactions for this rule
    existing = {
        t.rule_date
        for t in db.query(Transaction.rule_date)
        .filter(Transaction.rule_id == rule_id, Transaction.deleted_at.is_(None))
        .all()
        if t.rule_date
    }
    skipped = {
        s.skip_date
        for s in db.query(RecurringSkip.skip_date)
        .filter(RecurringSkip.rule_id == rule_id)
        .all()
    }

    created = []
    now = int(time.time())
    for occ in occurrences:
        occ_str = occ.isoformat()
        if occ_str in existing or occ_str in skipped:
            continue
        txn = Transaction(
            scope=rule.scope,
            type=rule.type,
            amount=rule.amount,
            category=rule.category,
            description=rule.description,
            date=occ_str,
            entity_id=rule.entity_id,
            payment_method=rule.payment_method,
            tags=rule.tags,
            meta=rule.meta,
            rule_id=rule_id,
            rule_date=occ_str,
            created_by=agent.agent_id,
            created_at=now,
            updated_at=now,
        )
        db.add(txn)
        created.append(occ_str)

    db.commit()
    return {
        "data": {"rule_id": rule_id, "created": len(created), "dates": created}
    }


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Soft-delete a recurring rule. Existing transaction instances are kept."""
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")
    rule = get_scoped_or_404(db, RecurringRule, rule_id, agent)
    rule.deleted_at = int(time.time())
    rule.updated_by = agent.agent_id
    db.commit()
    return {"data": {"id": rule_id, "deleted": True}}
