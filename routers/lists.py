import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.connection import get_db
from db.helpers import active_query, apply_scope_filter, get_scoped_or_404
from db.models import ListItem
from dependencies import AgentPrincipal, get_current_agent, validate_scope
from schemas import ListItemCreate, ListItemOut, ListItemUpdate

router = APIRouter(
    prefix="/api/lists",
    tags=["lists"],
)


@router.get("")
def get_lists(
    scope: str | None = None,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Return distinct list names with item counts."""
    q = db.query(
        ListItem.list,
        func.count(ListItem.id).label("total"),
        func.sum(ListItem.checked).label("checked_count"),
    ).filter(ListItem.deleted_at.is_(None))
    if scope:
        if not agent.can_access_scope(scope):
            raise HTTPException(status_code=403, detail=f"No access to scope '{scope}'")
        q = q.filter(ListItem.scope == scope)
    elif "*" not in agent.allowed_scopes:
        q = q.filter(ListItem.scope.in_(agent.allowed_scopes))
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
    offset: int = Query(0, ge=0),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    q = apply_scope_filter(active_query(db, ListItem), ListItem, scope, agent)
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
def create_list_item(
    body: ListItemCreate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")
    validate_scope(body.scope)
    if not agent.can_access_scope(body.scope):
        raise HTTPException(status_code=403, detail=f"No write access to scope '{body.scope}'")

    # Auto-assign position if not provided
    if body.position is None:
        max_pos = (
            db.query(func.max(ListItem.position))
            .filter(
                ListItem.scope == body.scope,
                ListItem.list == body.list,
                ListItem.deleted_at.is_(None),
            )
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
        created_by=agent.agent_id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"data": ListItemOut.model_validate(item)}


@router.put("/items/{item_id}")
def update_list_item(
    item_id: str,
    body: ListItemUpdate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    item = get_scoped_or_404(db, ListItem, item_id, agent)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    item.updated_by = agent.agent_id
    db.commit()
    db.refresh(item)
    return {"data": ListItemOut.model_validate(item)}


@router.delete("/items/{item_id}")
def delete_list_item(
    item_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    item = get_scoped_or_404(db, ListItem, item_id, agent)
    item.deleted_at = int(time.time())
    item.updated_by = agent.agent_id
    db.commit()
    return {"data": {"id": item_id, "deleted": True}}


@router.delete("")
def clear_list(
    scope: str = Query(...),
    list: str = Query(...),
    checked_only: bool = Query(False),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Delete all items in a list. Use checked_only=true to remove only checked items."""
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")
    validate_scope(scope)
    if not agent.can_access_scope(scope):
        raise HTTPException(status_code=403, detail=f"No write access to scope '{scope}'")

    q = active_query(db, ListItem).filter(
        ListItem.scope == scope,
        ListItem.list == list,
    )
    if checked_only:
        q = q.filter(ListItem.checked.is_(True))
    count = q.count()
    q.update(
        {
            ListItem.deleted_at: int(time.time()),
            ListItem.updated_by: agent.agent_id,
        },
        synchronize_session=False,
    )
    db.commit()
    return {"data": {"list": list, "scope": scope, "deleted_count": count}}
