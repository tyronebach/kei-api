from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import Entity
from dependencies import verify_token
from schemas import EntityCreate, EntityOut, EntityUpdate

router = APIRouter(
    prefix="/api/entities",
    tags=["entities"],
    dependencies=[Depends(verify_token)],
)


@router.post("")
def create_entity(body: EntityCreate, db: Session = Depends(get_db)):
    entity = Entity(**body.model_dump(exclude_none=True))
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return {"data": EntityOut.model_validate(entity)}


@router.get("")
def list_entities(
    search: str | None = None,
    type: str | None = None,
    tag: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Entity)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                Entity.name.ilike(pattern),
                Entity.email.ilike(pattern),
                Entity.phone.ilike(pattern),
            )
        )
    if type:
        q = q.filter(Entity.type == type)
    if tag:
        q = q.filter(
            text(
                "EXISTS (SELECT 1 FROM json_each(entities.tags) WHERE json_each.value = :tag)"
            ).bindparams(tag=tag)
        )
    total = q.count()
    entities = (
        q.order_by(Entity.updated_at.desc()).offset(offset).limit(limit).all()
    )
    return {
        "data": [EntityOut.model_validate(e) for e in entities],
        "meta": {"count": len(entities), "total": total},
    }


@router.get("/{entity_id}")
def get_entity(entity_id: str, db: Session = Depends(get_db)):
    entity = db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"data": EntityOut.model_validate(entity)}


@router.put("/{entity_id}")
def update_entity(
    entity_id: str, body: EntityUpdate, db: Session = Depends(get_db)
):
    entity = db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(entity, key, value)
    db.commit()
    db.refresh(entity)
    return {"data": EntityOut.model_validate(entity)}


@router.delete("/{entity_id}")
def delete_entity(entity_id: str, db: Session = Depends(get_db)):
    entity = db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    db.delete(entity)
    db.commit()
    return {"data": {"id": entity_id, "deleted": True}}
