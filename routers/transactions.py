import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.connection import get_db
from db.helpers import active_query, apply_scope_filter, get_scoped_or_404
from db.models import Transaction
from dependencies import AgentPrincipal, get_current_agent, validate_scope
from schemas import TransactionCreate, TransactionOut, TransactionUpdate

router = APIRouter(
    prefix="/api/transactions",
    tags=["transactions"],
)


@router.post("")
def create_transaction(
    body: TransactionCreate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")
    validate_scope(body.scope)
    if not agent.can_access_scope(body.scope):
        raise HTTPException(status_code=403, detail=f"No write access to scope '{body.scope}'")

    txn = Transaction(**body.model_dump(exclude_none=True), created_by=agent.agent_id)
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
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    q = apply_scope_filter(active_query(db, Transaction), Transaction, scope, agent)
    if type:
        q = q.filter(Transaction.type == type)
    if category:
        categories = [c.strip() for c in category.split(",")]
        q = q.filter(Transaction.category.in_(categories))
    if entity_id:
        q = q.filter(Transaction.entity_id == entity_id)
    if from_date is not None:
        q = q.filter(Transaction.date >= from_date)
    if to_date is not None:
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
def get_transaction(
    transaction_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    txn = get_scoped_or_404(db, Transaction, transaction_id, agent)
    return {"data": TransactionOut.model_validate(txn)}


@router.put("/{transaction_id}")
def update_transaction(
    transaction_id: str,
    body: TransactionUpdate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    txn = get_scoped_or_404(db, Transaction, transaction_id, agent)
    if body.scope is not None:
        validate_scope(body.scope)
        if not agent.can_access_scope(body.scope):
            raise HTTPException(
                status_code=403,
                detail=f"No write access to scope '{body.scope}'",
            )

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(txn, key, value)
    txn.updated_by = agent.agent_id
    db.commit()
    db.refresh(txn)
    return {"data": TransactionOut.model_validate(txn)}


@router.delete("/{transaction_id}")
def delete_transaction(
    transaction_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    txn = get_scoped_or_404(db, Transaction, transaction_id, agent)
    txn.deleted_at = int(time.time())
    txn.updated_by = agent.agent_id
    db.commit()
    return {"data": {"id": transaction_id, "deleted": True}}
