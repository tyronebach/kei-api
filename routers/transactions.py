from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import Transaction
from dependencies import verify_token
from schemas import TransactionCreate, TransactionOut, TransactionUpdate

router = APIRouter(
    prefix="/api/transactions",
    tags=["transactions"],
    dependencies=[Depends(verify_token)],
)


@router.post("")
def create_transaction(body: TransactionCreate, db: Session = Depends(get_db)):
    txn = Transaction(**body.model_dump(exclude_none=True))
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return {"data": TransactionOut.model_validate(txn)}


@router.get("")
def list_transactions(
    scope: str | None = None,
    type: str | None = None,
    category: str | None = None,
    entity_id: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    sort: str = Query("date", pattern="^(date|created_at|amount)$"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Transaction)
    if scope:
        q = q.filter(Transaction.scope == scope)
    if type:
        q = q.filter(Transaction.type == type)
    if category:
        categories = [c.strip() for c in category.split(",")]
        q = q.filter(Transaction.category.in_(categories))
    if entity_id:
        q = q.filter(Transaction.entity_id == entity_id)
    if from_date:
        q = q.filter(Transaction.date >= from_date)
    if to_date:
        q = q.filter(Transaction.date <= to_date)
    total = q.count()

    sort_col = {
        "date": Transaction.date,
        "created_at": Transaction.created_at,
        "amount": Transaction.amount,
    }[sort]
    txns = (
        q.order_by(sort_col.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "data": [TransactionOut.model_validate(t) for t in txns],
        "meta": {"count": len(txns), "total": total},
    }


@router.get("/{transaction_id}")
def get_transaction(transaction_id: str, db: Session = Depends(get_db)):
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"data": TransactionOut.model_validate(txn)}


@router.put("/{transaction_id}")
def update_transaction(
    transaction_id: str, body: TransactionUpdate, db: Session = Depends(get_db)
):
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(txn, key, value)
    db.commit()
    db.refresh(txn)
    return {"data": TransactionOut.model_validate(txn)}


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: str, db: Session = Depends(get_db)):
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(txn)
    db.commit()
    return {"data": {"id": transaction_id, "deleted": True}}
