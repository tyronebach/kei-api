from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import Item, ItemMovement
from dependencies import verify_token
from schemas import (
    ItemAdjust,
    ItemCreate,
    ItemMovementOut,
    ItemOut,
    ItemSearchOut,
    ItemUpdate,
)
from search import determine_confidence, score_record

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
    scope: str | None = None,
    search: str | None = None,
    category: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Item)

    # DB-level filters (exact match, fast)
    if scope:
        q = q.filter(Item.scope == scope)
    if category:
        q = q.filter(Item.category == category)

    # Fuzzy search: score in Python for typo tolerance
    if search:
        candidates = q.all()
        scored = []
        for item in candidates:
            data = ItemOut.model_validate(item).model_dump()
            result = score_record(
                query=search,
                record_id=item.id,
                fields=["name", "category", "notes"],
                data=data,
            )
            if result:
                scored.append(result)

        scored.sort(key=lambda r: r.score, reverse=True)
        confident, best_match = determine_confidence(scored)

        page = scored[offset : offset + limit]
        return {
            "data": [
                ItemSearchOut(**r.data, score=r.score, match_type=r.match_type)
                for r in page
            ],
            "meta": {
                "count": len(page),
                "total": len(scored),
                "query": search,
                "confident": confident,
                "best_match": best_match,
            },
        }

    # No search: standard listing
    total = q.count()
    items = q.order_by(Item.updated_at.desc()).offset(offset).limit(limit).all()
    return {
        "data": [ItemOut.model_validate(i) for i in items],
        "meta": {"count": len(items), "total": total},
    }


@router.get("/low-stock")
def list_low_stock(scope: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Item).filter(
        Item.reorder_threshold.isnot(None),
        Item.quantity <= Item.reorder_threshold,
    )
    if scope:
        q = q.filter(Item.scope == scope)
    items = q.order_by(Item.quantity.asc()).all()
    return {
        "data": [ItemOut.model_validate(i) for i in items],
        "meta": {"count": len(items)},
    }


@router.get("/{item_id}")
def get_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"data": ItemOut.model_validate(item)}


@router.get("/{item_id}/movements")
def list_item_movements(
    item_id: str,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    q = db.query(ItemMovement).filter(ItemMovement.item_id == item_id)
    total = q.count()
    movements = (
        q.order_by(ItemMovement.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "data": [ItemMovementOut.model_validate(m) for m in movements],
        "meta": {"count": len(movements), "total": total},
    }


@router.post("/{item_id}/adjust")
def adjust_item(item_id: str, body: ItemAdjust, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if body.type == "in":
        item.quantity += body.quantity
    elif body.type == "out":
        if item.quantity < body.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock: {item.quantity} {item.unit} available",
            )
        item.quantity -= body.quantity
    elif body.type == "adjustment":
        item.quantity = body.quantity

    movement = ItemMovement(
        item_id=item_id,
        type=body.type,
        quantity=body.quantity,
        reason=body.reason,
        transaction_id=body.transaction_id,
    )
    db.add(movement)
    db.commit()
    db.refresh(item)

    return {
        "data": ItemOut.model_validate(item),
        "meta": {"movement_id": movement.id},
    }


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
