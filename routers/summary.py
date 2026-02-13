from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import Transaction
from dependencies import verify_token

router = APIRouter(
    prefix="/api/summary",
    tags=["summary"],
    dependencies=[Depends(verify_token)],
)


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


@router.get("")
def get_summary(
    period: str = Query("month"),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    db: Session = Depends(get_db),
):
    start, end = _resolve_period(period, from_date, to_date)

    # Income / expense totals
    rows = (
        db.query(
            Transaction.type,
            func.sum(Transaction.amount).label("total"),
            func.count().label("count"),
        )
        .filter(Transaction.date >= start, Transaction.date <= end)
        .group_by(Transaction.type)
        .all()
    )

    income = {"total": 0.0, "count": 0}
    expenses = {"total": 0.0, "count": 0}
    for row in rows:
        bucket = {"total": round(row.total, 2), "count": row.count}
        if row.type == "income":
            income = bucket
        elif row.type == "expense":
            expenses = bucket

    # Top income categories
    top_cats = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count().label("count"),
        )
        .filter(
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.type == "income",
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .limit(5)
        .all()
    )

    return {
        "data": {
            "period": {"from": start, "to": end},
            "income": income,
            "expenses": expenses,
            "profit": round(income["total"] - expenses["total"], 2),
            "top_categories": [
                {
                    "category": c.category,
                    "total": round(c.total, 2),
                    "count": c.count,
                }
                for c in top_cats
            ],
        }
    }
