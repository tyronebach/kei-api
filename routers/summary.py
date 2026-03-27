from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func, literal_column
from sqlalchemy.orm import Session

from db.connection import get_db
from db.helpers import apply_scope_filter
from db.models import Entity, Item, Transaction
from dependencies import AgentPrincipal, get_current_agent
from utils import parse_date

router = APIRouter(
    prefix="/api/summary",
    tags=["summary"],
)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _resolve_period(
    period: str, from_date: str | None, to_date: str | None
) -> tuple[str, str]:
    today = date.today()
    if period == "today":
        return str(today), str(today)
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        return str(start), str(today)
    elif period == "month":
        return f"{today.year}-{today.month:02d}-01", str(today)
    elif period == "year":
        return f"{today.year}-01-01", str(today)
    elif period == "custom":
        if not from_date or not to_date:
            raise HTTPException(
                status_code=422,
                detail="Custom period requires both 'from' and 'to' dates.",
            )
        start = parse_date(from_date, "from")
        end = parse_date(to_date, "to")
        if start > end:
            raise HTTPException(
                status_code=422,
                detail="'from' date must be less than or equal to 'to' date.",
            )
        return start.isoformat(), end.isoformat()
    return f"{today.year}-{today.month:02d}-01", str(today)


def _previous_period(start: str, end: str) -> tuple[str, str]:
    """Compute the previous period of the same length."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    duration = (e - s).days + 1
    prev_end = s - timedelta(days=1)
    prev_start = prev_end - timedelta(days=duration - 1)
    return str(prev_start), str(prev_end)


def _apply_source_filter(q, source: str | None, payment_method: str | None):
    """Apply source and payment_method filters to a query.

    source mapping:
      bank  → external_source == "tributary"
      cash  → payment_method == "cash"
      agent → external_source IS NULL AND payment_method != "cash"
      all / None → no filter
    """
    if source == "bank":
        q = q.filter(Transaction.external_source == "tributary")
    elif source == "cash":
        q = q.filter(Transaction.payment_method == "cash")
    elif source == "agent":
        q = q.filter(
            Transaction.external_source.is_(None),
            Transaction.payment_method != "cash",
        )
    # source == "all" or None → no filter

    if payment_method is not None:
        q = q.filter(Transaction.payment_method == payment_method)

    return q


def _period_totals(
    db: Session,
    start: str,
    end: str,
    agent: AgentPrincipal,
    scope: str | None = None,
    payment_method: str | None = None,
    source: str | None = None,
) -> dict:
    """Compute income/expense totals for a date range.
    Amounts are stored as integer cents; output is dollars (divided by 100).
    """
    q = db.query(
        Transaction.type,
        func.sum(Transaction.amount).label("total_cents"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.deleted_at.is_(None),
    )
    q = apply_scope_filter(q, Transaction, scope, agent)
    q = _apply_source_filter(q, source, payment_method)
    rows = q.group_by(Transaction.type).all()
    income = {"total": 0.0, "count": 0}
    expenses = {"total": 0.0, "count": 0}
    for row in rows:
        bucket = {"total": round((row.total_cents or 0) / 100, 2), "count": row.count}
        if row.type == "income":
            income = bucket
        elif row.type == "expense":
            expenses = bucket
    return {"income": income, "expenses": expenses}


@router.get("")
def get_summary(
    scope: str | None = None,
    period: str = Query("month"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    payment_method: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    start, end = _resolve_period(period, from_date, to_date)
    totals = _period_totals(db, start, end, agent, scope, payment_method, source)
    income = totals["income"]
    expenses = totals["expenses"]

    # Top income categories
    top_income_q = db.query(
        Transaction.category,
        func.sum(Transaction.amount).label("total_cents"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.type == "income",
        Transaction.deleted_at.is_(None),
    )
    top_income_q = apply_scope_filter(top_income_q, Transaction, scope, agent)
    top_income_q = _apply_source_filter(top_income_q, source, payment_method)
    top_income = (
        top_income_q.group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(5)
        .all()
    )

    # Top expense categories
    top_expense_q = db.query(
        Transaction.category,
        func.sum(Transaction.amount).label("total_cents"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.type == "expense",
        Transaction.deleted_at.is_(None),
    )
    top_expense_q = apply_scope_filter(top_expense_q, Transaction, scope, agent)
    top_expense_q = _apply_source_filter(top_expense_q, source, payment_method)
    top_expense = (
        top_expense_q.group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(5)
        .all()
    )

    # Client metrics
    active_q = db.query(distinct(Transaction.entity_id)).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.type == "income",
        Transaction.entity_id.isnot(None),
        Transaction.deleted_at.is_(None),
    )
    active_q = apply_scope_filter(active_q, Transaction, scope, agent)
    active_ids = active_q.all()
    active_count = len(active_ids)

    start_epoch = int(date.fromisoformat(start).strftime("%s"))
    end_epoch = int(
        (date.fromisoformat(end) + timedelta(days=1)).strftime("%s")
    )
    new_q = db.query(func.count(Entity.id)).filter(
        Entity.created_at >= start_epoch,
        Entity.created_at < end_epoch,
        Entity.deleted_at.is_(None),
    )
    new_q = apply_scope_filter(new_q, Entity, scope, agent)
    new_count = new_q.scalar()

    # Inventory alerts
    low_stock_q = db.query(func.count(Item.id)).filter(
        Item.reorder_threshold.isnot(None),
        Item.quantity <= Item.reorder_threshold,
        Item.deleted_at.is_(None),
    )
    low_stock_q = apply_scope_filter(low_stock_q, Item, scope, agent)
    low_stock_count = low_stock_q.scalar()

    def _fmt_cats(rows):
        return [
            {"category": c.category, "total": round(c.total_cents / 100, 2), "count": c.count}
            for c in rows
        ]

    return {
        "data": {
            "period": {"from": start, "to": end},
            "income": income,
            "expenses": expenses,
            "profit": round(income["total"] - expenses["total"], 2),
            "top_income": _fmt_cats(top_income),
            "top_expenses": _fmt_cats(top_expense),
            "clients": {
                "active": active_count,
                "new": new_count,
                "returning": max(active_count - new_count, 0),
            },
            "inventory_alerts": low_stock_count,
        }
    }


@router.get("/trends")
def get_trends(
    scope: str | None = None,
    period: str = Query("month"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    payment_method: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    start, end = _resolve_period(period, from_date, to_date)
    prev_start, prev_end = _previous_period(start, end)

    current = _period_totals(db, start, end, agent, scope, payment_method, source)
    previous = _period_totals(db, prev_start, prev_end, agent, scope, payment_method, source)

    cur_profit = current["income"]["total"] - current["expenses"]["total"]
    prev_profit = previous["income"]["total"] - previous["expenses"]["total"]

    def _change(cur: float, prev: float) -> dict:
        diff = round(cur - prev, 2)
        pct = round((diff / prev) * 100, 1) if prev else 0.0
        return {"amount": diff, "percent": pct}

    income_change = _change(current["income"]["total"], previous["income"]["total"])

    # Determine trend
    if income_change["percent"] > 5:
        trend = "up"
    elif income_change["percent"] < -5:
        trend = "down"
    else:
        trend = "stable"

    return {
        "data": {
            "current": {
                "period": {"from": start, "to": end},
                "income": current["income"]["total"],
                "expenses": current["expenses"]["total"],
                "profit": round(cur_profit, 2),
            },
            "previous": {
                "period": {"from": prev_start, "to": prev_end},
                "income": previous["income"]["total"],
                "expenses": previous["expenses"]["total"],
                "profit": round(prev_profit, 2),
            },
            "change": {
                "income": _change(
                    current["income"]["total"], previous["income"]["total"]
                ),
                "expenses": _change(
                    current["expenses"]["total"], previous["expenses"]["total"]
                ),
                "profit": _change(cur_profit, prev_profit),
            },
            "trend": trend,
        }
    }


@router.get("/by-scope")
def get_summary_by_scope(
    scope: str | None = None,
    period: str = Query("month"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    payment_method: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    start, end = _resolve_period(period, from_date, to_date)

    q = db.query(
        Transaction.scope,
        Transaction.type,
        func.sum(Transaction.amount).label("total_cents"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.deleted_at.is_(None),
    )
    q = apply_scope_filter(q, Transaction, scope, agent)
    q = _apply_source_filter(q, source, payment_method)
    rows = q.group_by(Transaction.scope, Transaction.type).all()

    per_scope: dict[str, dict] = {}
    for row in rows:
        if row.scope not in per_scope:
            per_scope[row.scope] = {
                "scope": row.scope,
                "income": {"total": 0.0, "count": 0},
                "expenses": {"total": 0.0, "count": 0},
            }
        bucket = {"total": round((row.total_cents or 0) / 100, 2), "count": row.count}
        if row.type == "income":
            per_scope[row.scope]["income"] = bucket
        elif row.type == "expense":
            per_scope[row.scope]["expenses"] = bucket

    scopes = sorted(per_scope.values(), key=lambda row: row["scope"])
    for row in scopes:
        row["profit"] = round(row["income"]["total"] - row["expenses"]["total"], 2)

    return {
        "data": {
            "period": {"from": start, "to": end},
            "scopes": scopes,
        },
        "meta": {"count": len(scopes)},
    }


@router.get("/by-day")
def get_by_day(
    scope: str | None = None,
    period: str = Query("month"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    payment_method: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    start, end = _resolve_period(period, from_date, to_date)

    # SQLite strftime('%w', date) returns '0'=Sunday .. '6'=Saturday
    q = db.query(
        literal_column("CAST(strftime('%w', transactions.date) AS INTEGER)").label(
            "dow"
        ),
        func.sum(Transaction.amount).label("total_cents"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.type == "income",
        Transaction.deleted_at.is_(None),
    )
    q = apply_scope_filter(q, Transaction, scope, agent)
    q = _apply_source_filter(q, source, payment_method)
    rows = q.group_by(literal_column("1")).all()

    # Build full week (all 7 days), SQLite dow: 0=Sun,1=Mon..6=Sat
    # Convert to Monday-first: Mon=0..Sun=6
    sqlite_to_monday = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 0: 6}
    by_day = {i: {"day": DAY_NAMES[i], "total": 0.0, "count": 0} for i in range(7)}
    for row in rows:
        idx = sqlite_to_monday[row.dow]
        by_day[idx] = {
            "day": DAY_NAMES[idx],
            "total": round((row.total_cents or 0) / 100, 2),
            "count": row.count,
        }

    days = [by_day[i] for i in range(7)]
    busiest = max(days, key=lambda d: d["total"])

    return {
        "data": {
            "period": {"from": start, "to": end},
            "days": days,
            "busiest": busiest["day"],
        }
    }


@router.get("/by-category")
def get_by_category(
    scope: str | None = None,
    period: str = Query("month"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    type: str | None = Query(None, description="Filter: income or expense"),
    payment_method: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    limit: int = Query(20, ge=1, le=100),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Return categories ranked by total amount, grouped by type."""
    start, end = _resolve_period(period, from_date, to_date)

    q = db.query(
        Transaction.category,
        Transaction.type,
        func.sum(Transaction.amount).label("total_cents"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.deleted_at.is_(None),
    )
    q = apply_scope_filter(q, Transaction, scope, agent)
    q = _apply_source_filter(q, source, payment_method)

    if type and type in ("income", "expense"):
        q = q.filter(Transaction.type == type)

    rows = q.group_by(Transaction.category, Transaction.type).all()

    # Compute type totals for percent calculation
    type_totals: dict[str, float] = {"income": 0.0, "expense": 0.0}
    for row in rows:
        type_totals[row.type] = type_totals.get(row.type, 0.0) + (row.total_cents or 0)

    categories = []
    for row in rows:
        total_dollars = round((row.total_cents or 0) / 100, 2)
        type_total = type_totals.get(row.type, 0)
        pct = round(((row.total_cents or 0) / type_total) * 100, 1) if type_total else 0.0
        categories.append({
            "category": row.category,
            "type": row.type,
            "total": total_dollars,
            "count": row.count,
            "percent": pct,
        })

    # Sort by total descending
    categories.sort(key=lambda c: c["total"], reverse=True)
    categories = categories[:limit]

    return {
        "data": {
            "period": {"from": start, "to": end},
            "categories": categories,
            "totals": {
                "income": round(type_totals.get("income", 0) / 100, 2),
                "expenses": round(type_totals.get("expense", 0) / 100, 2),
            },
        }
    }


@router.get("/by-month")
def get_by_month(
    scope: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    payment_method: Annotated[str | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Return income/expense totals grouped by month.

    Defaults to the last 12 months if from/to not provided.
    Fills months with no data as 0s.
    """
    today = date.today()
    if from_date is None:
        # Last 12 months: start of month 11 months ago
        start_month = today.replace(day=1) - timedelta(days=today.replace(day=1).toordinal() - 1)
        # Simpler: subtract ~365 days and go to start of that month
        start_d = (today - timedelta(days=365)).replace(day=1)
        start = start_d.isoformat()
    else:
        start = parse_date(from_date, "from").isoformat()

    if to_date is None:
        end = today.isoformat()
    else:
        end = parse_date(to_date, "to").isoformat()

    # Query grouped by YYYY-MM
    q = db.query(
        literal_column("strftime('%Y-%m', transactions.date)").label("month"),
        Transaction.type,
        func.sum(Transaction.amount).label("total_cents"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.deleted_at.is_(None),
    )
    q = apply_scope_filter(q, Transaction, scope, agent)
    q = _apply_source_filter(q, source, payment_method)
    rows = q.group_by(
        literal_column("strftime('%Y-%m', transactions.date)"),
        Transaction.type,
    ).all()

    # Build month range
    start_d = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    # Generate all YYYY-MM strings in range
    months_in_range: list[str] = []
    cur = start_d.replace(day=1)
    while cur <= end_d:
        months_in_range.append(cur.strftime("%Y-%m"))
        # Advance to next month
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    # Build data map
    month_data: dict[str, dict] = {
        m: {
            "month": m,
            "income": 0.0,
            "expenses": 0.0,
            "profit": 0.0,
            "income_count": 0,
            "expense_count": 0,
        }
        for m in months_in_range
    }

    for row in rows:
        m = row.month
        if m not in month_data:
            continue
        if row.type == "income":
            month_data[m]["income"] = round((row.total_cents or 0) / 100, 2)
            month_data[m]["income_count"] = row.count
        elif row.type == "expense":
            month_data[m]["expenses"] = round((row.total_cents or 0) / 100, 2)
            month_data[m]["expense_count"] = row.count

    # Compute profit
    for m in month_data.values():
        m["profit"] = round(m["income"] - m["expenses"], 2)

    months_list = [month_data[m] for m in months_in_range]

    return {
        "data": {
            "period": {"from": start, "to": end},
            "months": months_list,
        },
        "meta": {"count": len(months_list)},
    }
