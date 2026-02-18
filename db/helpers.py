from fastapi import HTTPException
from sqlalchemy.orm import Session


def active_query(db: Session, model):
    return db.query(model).filter(model.deleted_at.is_(None))


def get_active_by_id(db: Session, model, record_id: str):
    return (
        db.query(model)
        .filter(
            model.id == record_id,
            model.deleted_at.is_(None),
        )
        .first()
    )


def apply_scope_filter(query, model, scope: str | None, agent):
    if scope:
        if not agent.can_access_scope(scope):
            raise HTTPException(status_code=403, detail=f"No access to scope '{scope}'")
        return query.filter(model.scope == scope)

    if "*" not in agent.allowed_scopes:
        return query.filter(model.scope.in_(agent.allowed_scopes))

    return query


def get_scoped_or_404(db: Session, model, record_id: str, agent):
    record = get_active_by_id(db, model, record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    if not agent.can_access_scope(record.scope):
        raise HTTPException(status_code=403, detail="No access to this record's scope")
    return record
