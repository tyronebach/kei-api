from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import Transaction
from dependencies import AgentPrincipal, get_current_agent

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
)


@router.get("")
def get_audit_stats(
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    soft_deleted_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.deleted_at.isnot(None))
        .scalar()
    )

    active_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.deleted_at.is_(None))
        .scalar()
    )

    content_duplicate_count = db.execute(
        text("""
            SELECT COUNT(*) FROM (
                SELECT scope, date, amount, description
                FROM transactions
                WHERE deleted_at IS NULL
                GROUP BY scope, date, amount, description
                HAVING COUNT(*) > 1
            )
        """)
    ).scalar()

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
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Write permission required")

    count = (
        db.query(Transaction)
        .filter(Transaction.deleted_at.isnot(None))
        .delete(synchronize_session=False)
    )
    db.commit()

    return {"deleted_count": count}
