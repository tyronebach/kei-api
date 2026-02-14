from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import Service
from dependencies import verify_token
from schemas import ServiceCreate, ServiceOut, ServiceUpdate

router = APIRouter(
    prefix="/api/services",
    tags=["services"],
    dependencies=[Depends(verify_token)],
)


@router.post("")
def create_service(body: ServiceCreate, db: Session = Depends(get_db)):
    service = Service(**body.model_dump(exclude_none=True))
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
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Service)

    if scope:
        q = q.filter(Service.scope == scope)
    if category:
        q = q.filter(Service.category == category)

    total = q.count()
    services = (
        q.order_by(Service.name.asc()).offset(offset).limit(limit).all()
    )
    return {
        "data": [ServiceOut.model_validate(s) for s in services],
        "meta": {"count": len(services), "total": total},
    }


@router.get("/{service_id}")
def get_service(service_id: str, db: Session = Depends(get_db)):
    service = db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return {"data": ServiceOut.model_validate(service)}


@router.put("/{service_id}")
def update_service(
    service_id: str, body: ServiceUpdate, db: Session = Depends(get_db)
):
    service = db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(service, key, value)
    db.commit()
    db.refresh(service)
    return {"data": ServiceOut.model_validate(service)}


@router.delete("/{service_id}")
def delete_service(service_id: str, db: Session = Depends(get_db)):
    service = db.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    db.delete(service)
    db.commit()
    return {"data": {"id": service_id, "deleted": True}}
