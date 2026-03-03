import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import update
from sqlalchemy.orm import Session

from db.connection import get_db
from db.helpers import active_query, apply_scope_filter, get_scoped_or_404
from db.models import Item, ItemMovement
from dependencies import AgentPrincipal, get_current_agent, validate_scope
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
)


@router.post("")
def create_item(
    body: ItemCreate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")
    validate_scope(body.scope)
    if not agent.can_access_scope(body.scope):
        raise HTTPException(status_code=403, detail=f"No write access to scope '{body.scope}'")

    item = Item(**body.model_dump(exclude_none=True), created_by=agent.agent_id)
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
    offset: int = Query(0, ge=0),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    q = apply_scope_filter(active_query(db, Item), Item, scope, agent)

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
def list_low_stock(
    scope: str | None = None,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    q = apply_scope_filter(active_query(db, Item), Item, scope, agent).filter(
        Item.reorder_threshold.isnot(None),
        Item.quantity <= Item.reorder_threshold,
    )
    items = q.order_by(Item.quantity.asc()).all()
    return {
        "data": [ItemOut.model_validate(i) for i in items],
        "meta": {"count": len(items)},
    }


@router.get("/{item_id}")
def get_item(
    item_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    item = get_scoped_or_404(db, Item, item_id, agent)
    return {"data": ItemOut.model_validate(item)}


@router.get("/{item_id}/movements")
def list_item_movements(
    item_id: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    get_scoped_or_404(db, Item, item_id, agent)
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
def adjust_item(
    item_id: str,
    body: ItemAdjust,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    item = get_scoped_or_404(db, Item, item_id, agent)

    if body.type == "in":
        stmt = (
            update(Item)
            .where(
                Item.id == item_id,
                Item.deleted_at.is_(None),
                Item.scope == item.scope,
            )
            .values(quantity=Item.quantity + body.quantity, updated_by=agent.agent_id)
        )
    elif body.type == "out":
        stmt = (
            update(Item)
            .where(
                Item.id == item_id,
                Item.deleted_at.is_(None),
                Item.scope == item.scope,
                Item.quantity >= body.quantity,
            )
            .values(quantity=Item.quantity - body.quantity, updated_by=agent.agent_id)
        )
    elif body.type == "adjustment":
        stmt = (
            update(Item)
            .where(
                Item.id == item_id,
                Item.deleted_at.is_(None),
                Item.scope == item.scope,
            )
            .values(quantity=body.quantity, updated_by=agent.agent_id)
        )

    result = db.execute(stmt)
    if result.rowcount == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Insufficient stock: {item.quantity} {item.unit} available, "
                f"requested {body.quantity}"
            ),
        )

    movement = ItemMovement(
        item_id=item_id,
        type=body.type,
        quantity=body.quantity,
        reason=body.reason,
        transaction_id=body.transaction_id,
    )
    db.add(movement)
    db.flush()
    movement_id = movement.id
    db.commit()
    item = get_scoped_or_404(db, Item, item_id, agent)

    return {
        "data": ItemOut.model_validate(item),
        "meta": {"movement_id": movement_id},
    }


@router.put("/{item_id}")
def update_item(
    item_id: str,
    body: ItemUpdate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    item = get_scoped_or_404(db, Item, item_id, agent)
    if body.scope is not None:
        validate_scope(body.scope)
        if not agent.can_access_scope(body.scope):
            raise HTTPException(
                status_code=403,
                detail=f"No write access to scope '{body.scope}'",
            )

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    item.updated_by = agent.agent_id
    db.commit()
    db.refresh(item)
    return {"data": ItemOut.model_validate(item)}


@router.delete("/{item_id}")
def delete_item(
    item_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    item = get_scoped_or_404(db, Item, item_id, agent)
    item.deleted_at = int(time.time())
    item.updated_by = agent.agent_id
    db.commit()
    return {"data": {"id": item_id, "deleted": True}}
