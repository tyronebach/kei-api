from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.connection import get_db
from db.helpers import apply_scope_filter
from db.models import Transaction
from dependencies import AgentPrincipal, get_current_agent

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
)


@router.get("")
def get_audit_stats(
    scope: str | None = None,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    soft_deleted_q = db.query(func.count(Transaction.id)).filter(
        Transaction.deleted_at.isnot(None),
    )
    soft_deleted_count = apply_scope_filter(
        soft_deleted_q,
        Transaction,
        scope,
        agent,
    ).scalar()

    active_q = db.query(func.count(Transaction.id)).filter(
        Transaction.deleted_at.is_(None),
    )
    active_count = apply_scope_filter(active_q, Transaction, scope, agent).scalar()

    duplicate_groups_q = db.query(
        Transaction.scope,
        Transaction.date,
        Transaction.amount,
        Transaction.description,
    ).filter(Transaction.deleted_at.is_(None))
    duplicate_groups_q = apply_scope_filter(duplicate_groups_q, Transaction, scope, agent)
    duplicate_groups = (
        duplicate_groups_q
        .group_by(
            Transaction.scope,
            Transaction.date,
            Transaction.amount,
            Transaction.description,
        )
        .having(func.count(Transaction.id) > 1)
        .subquery()
    )
    content_duplicate_count = db.query(func.count()).select_from(duplicate_groups).scalar()

    return {
        "soft_deleted_count": soft_deleted_count,
        "content_duplicate_count": content_duplicate_count,
        "active_count": active_count,
    }


@router.delete("/soft-deleted")
def purge_soft_deleted(
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Write permission required")
    if "*" not in agent.allowed_scopes:
        raise HTTPException(status_code=403, detail="Wildcard write permission required")

    count = (
        db.query(Transaction)
        .filter(Transaction.deleted_at.isnot(None))
        .delete(synchronize_session=False)
    )
    db.commit()

    return {"deleted_count": count}
