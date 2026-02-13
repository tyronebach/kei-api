from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import Item
from dependencies import verify_token
from schemas import ItemCreate, ItemOut, ItemUpdate

router = APIRouter(
    prefix="/api/items",
    tags=["items"],
    dependencies=[Depends(verify_token)],
)


@router.post("")
def create_item(body: ItemCreate, db: Session = Depends(get_db)):
    item = Item(**body.model_dump(exclude_none=True))
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"data": ItemOut.model_validate(item)}


@router.get("")
def list_items(
    search: str | None = None,
    category: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Item)
    if search:
        q = q.filter(Item.name.ilike(f"%{search}%"))
    if category:
        q = q.filter(Item.category == category)
    total = q.count()
    items = q.order_by(Item.updated_at.desc()).offset(offset).limit(limit).all()
    return {
        "data": [ItemOut.model_validate(i) for i in items],
        "meta": {"count": len(items), "total": total},
    }


@router.get("/{item_id}")
def get_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"data": ItemOut.model_validate(item)}


@router.put("/{item_id}")
def update_item(item_id: str, body: ItemUpdate, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return {"data": ItemOut.model_validate(item)}


@router.delete("/{item_id}")
def delete_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"data": {"id": item_id, "deleted": True}}
