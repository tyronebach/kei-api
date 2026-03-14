import time
from datetime import date as date_type, timedelta

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from db.connection import get_db
from db.helpers import active_query, apply_scope_filter, get_scoped_or_404
from db.models import Entity, Transaction
from dependencies import AgentPrincipal, get_current_agent, validate_scope
from schemas import TransactionCreate, TransactionOut, TransactionUpdate

router = APIRouter(
    prefix="/api/transactions",
    tags=["transactions"],
)


def _dollars_to_cents(amount: float) -> int:
    return round(amount * 100)


def _fuzzy_score(
    new_amount_cents: int,
    new_description: str | None,
    new_date: str,
    candidate: Transaction,
) -> int:
    """Return a 0-100 duplicate likelihood score for a candidate transaction.

    Weights: amount 40%, description 40%, date 20%.
    Returns 0 immediately if amount is too far off or date is outside ±3 days.
    """
    # Amount score — must be close or we don't bother
    if candidate.amount == new_amount_cents:
        amount_score = 100
    elif abs(candidate.amount - new_amount_cents) / max(new_amount_cents, 1) <= 0.05:
        amount_score = 80
    else:
        return 0

    # Description score — 0 when either side is null
    if new_description is None or candidate.description is None:
        desc_score = 0
    else:
        desc_score = fuzz.token_sort_ratio(new_description, candidate.description)

    # Date proximity score
    new_d = date_type.fromisoformat(new_date)
    cand_d = date_type.fromisoformat(candidate.date)
    days_diff = abs((new_d - cand_d).days)
    if days_diff == 0:
        date_score = 100
    elif days_diff == 1:
        date_score = 80
    elif days_diff == 2:
        date_score = 60
    elif days_diff == 3:
        date_score = 40
    else:
        return 0  # outside window (shouldn't happen given DB filter, but be safe)

    return int(amount_score * 0.4 + desc_score * 0.4 + date_score * 0.2)


def _find_fuzzy_duplicate(
    body: TransactionCreate,
    amount_cents: int,
    db: Session,
) -> tuple[Transaction | None, int]:
    """Query ±3-day window and return (best_candidate, score), or (None, 0)."""
    new_d = date_type.fromisoformat(body.date)
    date_min = (new_d - timedelta(days=3)).isoformat()
    date_max = (new_d + timedelta(days=3)).isoformat()

    candidates = (
        db.query(Transaction)
        .filter(
            Transaction.scope == body.scope,
            Transaction.type == body.type,
            Transaction.deleted_at.is_(None),
            Transaction.date >= date_min,
            Transaction.date <= date_max,
        )
        .all()
    )

    best: Transaction | None = None
    best_score = 0
    for c in candidates:
        score = _fuzzy_score(amount_cents, body.description, body.date, c)
        if score > best_score:
            best_score = score
            best = c

    return best, best_score


def _validate_entity_scope(entity_id: str | None, scope: str, db: Session) -> None:
    """Ensure the given entity belongs to the requested scope. Raises 422 if not."""
    if entity_id is None:
        return
    entity = db.query(Entity).filter(
        Entity.id == entity_id,
        Entity.deleted_at.is_(None),
    ).first()
    if entity is None:
        raise HTTPException(status_code=422, detail=f"Entity '{entity_id}' not found")
    if entity.scope != scope:
        raise HTTPException(
            status_code=422,
            detail=f"Entity '{entity_id}' belongs to scope '{entity.scope}', not '{scope}'",
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

    # Step 4: entity scope integrity
    _validate_entity_scope(body.entity_id, body.scope, db)

    # Step 2: idempotent ingest — if external identity matches existing row, return it
    if body.external_source and body.external_id:
        existing = db.query(Transaction).filter(
            Transaction.external_source == body.external_source,
            Transaction.external_id == body.external_id,
            Transaction.deleted_at.is_(None),
        ).first()
        if existing is not None:
            return {"data": TransactionOut.from_orm_cents(existing)}

    amount_cents = _dollars_to_cents(body.amount)

    # Step 3: fuzzy duplicate detection (manual writes only — skip if Tributary or force_create)
    probable_match: Transaction | None = None
    probable_score: int = 0
    if not body.external_source and not body.force_create:
        match, score = _find_fuzzy_duplicate(body, amount_cents, db)
        if match is not None and score >= 85:
            # High-confidence duplicate — do not insert
            return {"matched": True, "data": TransactionOut.from_orm_cents(match)}
        if match is not None and score >= 70:
            # Probable match — capture before insert, surface to caller after
            probable_match = match
            probable_score = score

    # Build ORM dict; exclude 'amount' and 'force_create' (handle separately or not stored)
    data = body.model_dump(exclude_none=True, exclude={"amount", "force_create"})
    data["amount"] = amount_cents
    data["created_by"] = agent.agent_id

    txn = Transaction(**data)
    db.add(txn)
    db.commit()
    db.refresh(txn)

    if probable_match is not None:
        return {
            "created": True,
            "probable_match": TransactionOut.from_orm_cents(probable_match),
            "match_score": probable_score,
        }

    return {"created": True, "data": TransactionOut.from_orm_cents(txn)}


@router.get("")
def list_transactions(
    scope: str | None = None,
    type: str | None = None,
    category: str | None = None,
    entity_id: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    payment_method: Annotated[str | None, Query()] = None,
    external_source: Annotated[str | None, Query()] = None,
    sort: str = Query("date", pattern="^(date|created_at|amount)$"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
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
    if payment_method is not None:
        q = q.filter(Transaction.payment_method == payment_method)
    if external_source is not None:
        q = q.filter(Transaction.external_source == external_source)
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
        "data": [TransactionOut.from_orm_cents(t) for t in txns],
        "meta": {"count": len(txns), "total": total},
    }


@router.get("/{transaction_id}")
def get_transaction(
    transaction_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    txn = get_scoped_or_404(db, Transaction, transaction_id, agent)
    return {"data": TransactionOut.from_orm_cents(txn)}


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

    # Step 4: entity scope integrity on update
    effective_scope = body.scope if body.scope is not None else txn.scope
    effective_entity_id = body.entity_id if "entity_id" in body.model_fields_set else txn.entity_id
    _validate_entity_scope(effective_entity_id, effective_scope, db)

    update_data = body.model_dump(exclude_unset=True)
    # Convert amount from dollars to cents if provided
    if "amount" in update_data:
        update_data["amount"] = _dollars_to_cents(update_data["amount"])

    for key, value in update_data.items():
        setattr(txn, key, value)
    txn.updated_by = agent.agent_id
    db.commit()
    db.refresh(txn)
    return {"data": TransactionOut.from_orm_cents(txn)}


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
