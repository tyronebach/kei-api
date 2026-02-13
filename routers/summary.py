from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, literal_column, text
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import Entity, Item, Transaction
from dependencies import verify_token

router = APIRouter(
    prefix="/api/summary",
    tags=["summary"],
    dependencies=[Depends(verify_token)],
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
    elif period == "custom" and from_date and to_date:
        return from_date, to_date
    return f"{today.year}-{today.month:02d}-01", str(today)


def _previous_period(start: str, end: str) -> tuple[str, str]:
    """Compute the previous period of the same length."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    duration = (e - s).days + 1
    prev_end = s - timedelta(days=1)
    prev_start = prev_end - timedelta(days=duration - 1)
    return str(prev_start), str(prev_end)


def _period_totals(
    db: Session, start: str, end: str, scope: str | None = None
) -> dict:
    """Compute income/expense totals for a date range."""
    q = db.query(
        Transaction.type,
        func.sum(Transaction.amount).label("total"),
        func.count().label("count"),
    ).filter(Transaction.date >= start, Transaction.date <= end)
    if scope:
        q = q.filter(Transaction.scope == scope)
    rows = q.group_by(Transaction.type).all()
    income = {"total": 0.0, "count": 0}
    expenses = {"total": 0.0, "count": 0}
    for row in rows:
        bucket = {"total": round(row.total, 2), "count": row.count}
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
    db: Session = Depends(get_db),
):
    start, end = _resolve_period(period, from_date, to_date)
    totals = _period_totals(db, start, end, scope)
    income = totals["income"]
    expenses = totals["expenses"]

    # Top income categories
    top_income_q = db.query(
        Transaction.category,
        func.sum(Transaction.amount).label("total"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.type == "income",
    )
    if scope:
        top_income_q = top_income_q.filter(Transaction.scope == scope)
    top_income = (
        top_income_q.group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(5)
        .all()
    )

    # Top expense categories
    top_expense_q = db.query(
        Transaction.category,
        func.sum(Transaction.amount).label("total"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.type == "expense",
    )
    if scope:
        top_expense_q = top_expense_q.filter(Transaction.scope == scope)
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
    )
    if scope:
        active_q = active_q.filter(Transaction.scope == scope)
    active_ids = active_q.all()
    active_count = len(active_ids)

    start_epoch = int(date.fromisoformat(start).strftime("%s"))
    end_epoch = int(
        (date.fromisoformat(end) + timedelta(days=1)).strftime("%s")
    )
    new_q = db.query(func.count(Entity.id)).filter(
        Entity.created_at >= start_epoch, Entity.created_at < end_epoch
    )
    if scope:
        new_q = new_q.filter(Entity.scope == scope)
    new_count = new_q.scalar()

    # Inventory alerts
    low_stock_q = db.query(func.count(Item.id)).filter(
        Item.reorder_threshold.isnot(None),
        Item.quantity <= Item.reorder_threshold,
    )
    if scope:
        low_stock_q = low_stock_q.filter(Item.scope == scope)
    low_stock_count = low_stock_q.scalar()

    def _fmt_cats(rows):
        return [
            {"category": c.category, "total": round(c.total, 2), "count": c.count}
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
    db: Session = Depends(get_db),
):
    start, end = _resolve_period(period, from_date, to_date)
    prev_start, prev_end = _previous_period(start, end)

    current = _period_totals(db, start, end, scope)
    previous = _period_totals(db, prev_start, prev_end, scope)

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


@router.get("/by-day")
def get_by_day(
    scope: str | None = None,
    period: str = Query("month"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    start, end = _resolve_period(period, from_date, to_date)

    # SQLite strftime('%w', date) returns '0'=Sunday .. '6'=Saturday
    q = db.query(
        literal_column("CAST(strftime('%w', transactions.date) AS INTEGER)").label(
            "dow"
        ),
        func.sum(Transaction.amount).label("total"),
        func.count().label("count"),
    ).filter(
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.type == "income",
    )
    if scope:
        q = q.filter(Transaction.scope == scope)
    rows = q.group_by(literal_column("1")).all()

    # Build full week (all 7 days), SQLite dow: 0=Sun,1=Mon..6=Sat
    # Convert to Monday-first: Mon=0..Sun=6
    sqlite_to_monday = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 0: 6}
    by_day = {i: {"day": DAY_NAMES[i], "total": 0.0, "count": 0} for i in range(7)}
    for row in rows:
        idx = sqlite_to_monday[row.dow]
        by_day[idx] = {
            "day": DAY_NAMES[idx],
            "total": round(row.total, 2),
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
