import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.connection import get_db
from db.helpers import active_query, apply_scope_filter, get_scoped_or_404
from db.models import Service
from dependencies import AgentPrincipal, get_current_agent, validate_scope
from schemas import ServiceCreate, ServiceOut, ServiceUpdate

router = APIRouter(
    prefix="/api/services",
    tags=["services"],
)


@router.post("")
def create_service(
    body: ServiceCreate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")
    validate_scope(body.scope)
    if not agent.can_access_scope(body.scope):
        raise HTTPException(status_code=403, detail=f"No write access to scope '{body.scope}'")

    service = Service(**body.model_dump(exclude_none=True), created_by=agent.agent_id)
    db.add(service)
    db.commit()
    db.refresh(service)
    return {"data": ServiceOut.model_validate(service)}


@router.get("")
def list_services(
    scope: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    q = apply_scope_filter(active_query(db, Service), Service, scope, agent)
    if category:
        q = q.filter(Service.category == category)
    if tag:
        q = q.filter(
            text(
                "EXISTS (SELECT 1 FROM json_each(services.tags) WHERE json_each.value = :tag)"
            ).bindparams(tag=tag)
        )

    total = q.count()
    services = (
        q.order_by(Service.name.asc()).offset(offset).limit(limit).all()
    )
    return {
        "data": [ServiceOut.model_validate(s) for s in services],
        "meta": {"count": len(services), "total": total},
    }


@router.get("/{service_id}")
def get_service(
    service_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    service = get_scoped_or_404(db, Service, service_id, agent)
    return {"data": ServiceOut.model_validate(service)}


@router.put("/{service_id}")
def update_service(
    service_id: str,
    body: ServiceUpdate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    service = get_scoped_or_404(db, Service, service_id, agent)
    if body.scope is not None:
        validate_scope(body.scope)
        if not agent.can_access_scope(body.scope):
            raise HTTPException(
                status_code=403,
                detail=f"No write access to scope '{body.scope}'",
            )

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(service, key, value)
    service.updated_by = agent.agent_id
    db.commit()
    db.refresh(service)
    return {"data": ServiceOut.model_validate(service)}


@router.delete("/{service_id}")
def delete_service(
    service_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    service = get_scoped_or_404(db, Service, service_id, agent)
    service.deleted_at = int(time.time())
    service.updated_by = agent.agent_id
    db.commit()
    return {"data": {"id": service_id, "deleted": True}}
