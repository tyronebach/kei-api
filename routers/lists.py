from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import ListItem
from dependencies import verify_token
from schemas import ListItemCreate, ListItemOut, ListItemUpdate

router = APIRouter(
    prefix="/api/lists",
    tags=["lists"],
    dependencies=[Depends(verify_token)],
)


@router.get("")
def get_lists(
    scope: str | None = None,
    db: Session = Depends(get_db),
):
    """Return distinct list names with item counts."""
    q = db.query(
        ListItem.list,
        func.count(ListItem.id).label("total"),
        func.sum(ListItem.checked).label("checked_count"),
    )
    if scope:
        q = q.filter(ListItem.scope == scope)
    rows = q.group_by(ListItem.list).order_by(ListItem.list).all()

    return {
        "data": [
            {
                "list": r.list,
                "total": r.total,
                "checked": int(r.checked_count or 0),
                "unchecked": r.total - int(r.checked_count or 0),
            }
            for r in rows
        ],
        "meta": {"count": len(rows)},
    }


@router.get("/items")
def list_items(
    scope: str | None = None,
    list: str | None = Query(None),
    checked: bool | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(ListItem)
    if scope:
        q = q.filter(ListItem.scope == scope)
    if list:
        q = q.filter(ListItem.list == list)
    if checked is not None:
        q = q.filter(ListItem.checked == checked)

    total = q.count()
    items = (
        q.order_by(ListItem.position.asc(), ListItem.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "data": [ListItemOut.model_validate(i) for i in items],
        "meta": {"count": len(items), "total": total},
    }


@router.post("/items")
def create_list_item(body: ListItemCreate, db: Session = Depends(get_db)):
    # Auto-assign position if not provided
    if body.position is None:
        max_pos = (
            db.query(func.max(ListItem.position))
            .filter(ListItem.scope == body.scope, ListItem.list == body.list)
            .scalar()
        )
        position = (max_pos or 0) + 1
    else:
        position = body.position

    item = ListItem(
        scope=body.scope,
        list=body.list,
        content=body.content,
        position=position,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"data": ListItemOut.model_validate(item)}


@router.put("/items/{item_id}")
def update_list_item(
    item_id: str, body: ListItemUpdate, db: Session = Depends(get_db)
):
    item = db.get(ListItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="List item not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return {"data": ListItemOut.model_validate(item)}


@router.delete("/items/{item_id}")
def delete_list_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(ListItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="List item not found")
    db.delete(item)
    db.commit()
    return {"data": {"id": item_id, "deleted": True}}


@router.delete("")
def clear_list(
    scope: str = Query(...),
    list: str = Query(...),
    checked_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Delete all items in a list. Use checked_only=true to remove only checked items."""
    q = db.query(ListItem).filter(
        ListItem.scope == scope,
        ListItem.list == list,
    )
    if checked_only:
        q = q.filter(ListItem.checked == True)
    count = q.count()
    q.delete(synchronize_session=False)
    db.commit()
    return {"data": {"list": list, "scope": scope, "deleted_count": count}}
