import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from db.connection import get_db
from db.helpers import active_query, apply_scope_filter, get_scoped_or_404
from db.models import Entity, Transaction
from dependencies import AgentPrincipal, get_current_agent, require_scope_write, validate_scope
from schemas import EntityCreate, EntityOut, EntitySearchOut, EntityUpdate
from search import determine_confidence, score_record
from utils import parse_date

router = APIRouter(
    prefix="/api/entities",
    tags=["entities"],
)


@router.post("")
def create_entity(
    body: EntityCreate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    require_scope_write(agent, body.scope)

    entity = Entity(**body.model_dump(exclude_none=True), created_by=agent.agent_id)
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return {"data": EntityOut.model_validate(entity)}


@router.get("")
def list_entities(
    scope: str | None = None,
    search: str | None = None,
    type: str | None = None,
    tag: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    q = apply_scope_filter(active_query(db, Entity), Entity, scope, agent)

    if type:
        q = q.filter(Entity.type == type)
    if tag:
        q = q.filter(
            text(
                "EXISTS (SELECT 1 FROM json_each(entities.tags) WHERE json_each.value = :tag)"
            ).bindparams(tag=tag)
        )

    # Fuzzy search: score in Python for typo tolerance
    if search:
        candidates = q.all()
        scored = []
        for entity in candidates:
            data = EntityOut.model_validate(entity).model_dump()
            result = score_record(
                query=search,
                record_id=entity.id,
                fields=["name", "email", "phone"],
                data=data,
            )
            if result:
                scored.append(result)

        scored.sort(key=lambda r: r.score, reverse=True)
        confident, best_match = determine_confidence(scored)

        page = scored[offset : offset + limit]
        return {
            "data": [
                EntitySearchOut(**r.data, score=r.score, match_type=r.match_type)
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
    entities = (
        q.order_by(Entity.updated_at.desc()).offset(offset).limit(limit).all()
    )
    return {
        "data": [EntityOut.model_validate(e) for e in entities],
        "meta": {"count": len(entities), "total": total},
    }


@router.get("/insights")
def get_entity_insights(
    scope: str | None = None,
    inactive_days: int | None = None,
    min_visits: int | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    sort: str = Query("last_visit", pattern="^(last_visit|total_spend|visits|name)$"),
    limit: int = Query(20, le=200),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    # Aggregate transaction activity per entity (income only = "visits")
    activity_q = db.query(
        Transaction.scope,
        Transaction.entity_id,
        func.count(Transaction.id).label("visit_count"),
        func.sum(Transaction.amount).label("total_spend"),
        func.max(Transaction.date).label("last_visit"),
    ).filter(
        Transaction.entity_id.isnot(None),
        Transaction.type == "income",
        Transaction.deleted_at.is_(None),
    )
    activity_q = apply_scope_filter(activity_q, Transaction, scope, agent)
    activity_rows = activity_q.group_by(Transaction.scope, Transaction.entity_id).all()
    activity = {(row.scope, row.entity_id): row for row in activity_rows}

    # Get entities with optional creation date filters
    q = apply_scope_filter(active_query(db, Entity), Entity, scope, agent)
    if created_after:
        created_after_date = parse_date(created_after, "created_after")
        epoch = int(datetime.combine(created_after_date, datetime.min.time()).timestamp())
        q = q.filter(Entity.created_at >= epoch)
    if created_before:
        created_before_date = parse_date(created_before, "created_before")
        day_after = created_before_date + timedelta(days=1)
        epoch = int(datetime.combine(day_after, datetime.min.time()).timestamp())
        q = q.filter(Entity.created_at < epoch)
    entities = q.all()

    # Enrich and filter
    today = date.today()
    results = []
    for e in entities:
        a = activity.get((e.scope, e.id))
        entry = {
            "id": e.id,
            "scope": e.scope,
            "name": e.name,
            "type": e.type,
            "visit_count": a.visit_count if a else 0,
            "total_spend": round((a.total_spend or 0) / 100, 2) if a else 0,
            "last_visit": a.last_visit if a else None,
        }

        if min_visits and entry["visit_count"] < min_visits:
            continue

        if inactive_days is not None:
            if entry["last_visit"]:
                last = date.fromisoformat(entry["last_visit"])
                if (today - last).days < inactive_days:
                    continue
            # entities with no visits are always "inactive"

        results.append(entry)

    # Sort
    sort_keys = {
        "last_visit": lambda r: r["last_visit"] or "",
        "total_spend": lambda r: r["total_spend"],
        "visits": lambda r: r["visit_count"],
        "name": lambda r: r["name"].lower(),
    }
    reverse = sort != "name"
    results.sort(key=sort_keys[sort], reverse=reverse)

    return {
        "data": results[:limit],
        "meta": {"count": len(results[:limit]), "total": len(results)},
    }


@router.get("/{entity_id}")
def get_entity(
    entity_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    entity = get_scoped_or_404(db, Entity, entity_id, agent)
    return {"data": EntityOut.model_validate(entity)}


@router.get("/{entity_id}/activity")
def get_entity_activity(
    entity_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    entity = get_scoped_or_404(db, Entity, entity_id, agent)

    # Aggregate income transactions for this entity
    stats = (
        db.query(
            func.count(Transaction.id).label("visit_count"),
            func.coalesce(func.sum(Transaction.amount), 0).label("total_spend"),
            func.min(Transaction.date).label("first_visit"),
            func.max(Transaction.date).label("last_visit"),
        )
        .filter(
            Transaction.entity_id == entity_id,
            Transaction.scope == entity.scope,
            Transaction.type == "income",
            Transaction.deleted_at.is_(None),
        )
        .first()
    )

    avg_spend = 0.0
    if stats.visit_count:
        avg_spend = round((stats.total_spend / stats.visit_count) / 100, 2)

    # Category breakdown
    categories = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count().label("count"),
        )
        .filter(
            Transaction.entity_id == entity_id,
            Transaction.scope == entity.scope,
            Transaction.type == "income",
            Transaction.deleted_at.is_(None),
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    # Recent transactions (last 5)
    recent = (
        db.query(Transaction)
        .filter(
            Transaction.entity_id == entity_id,
            Transaction.scope == entity.scope,
            Transaction.deleted_at.is_(None),
        )
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .limit(5)
        .all()
    )

    entity_out = EntityOut.model_validate(entity)

    return {
        "data": {
            **entity_out.model_dump(),
            "total_spend": round(float(stats.total_spend) / 100, 2),
            "visit_count": stats.visit_count,
            "first_visit": stats.first_visit,
            "last_visit": stats.last_visit,
            "avg_spend": avg_spend,
            "by_category": [
                {
                    "category": c.category,
                    "total": round((c.total or 0) / 100, 2),
                    "count": c.count,
                }
                for c in categories
            ],
            "recent_transactions": [
                {
                    "id": t.id,
                    "type": t.type,
                    "amount": round(t.amount / 100, 2),
                    "category": t.category,
                    "description": t.description,
                    "date": t.date,
                    "payment_method": t.payment_method,
                }
                for t in recent
            ],
        }
    }


@router.put("/{entity_id}")
def update_entity(
    entity_id: str,
    body: EntityUpdate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    entity = get_scoped_or_404(db, Entity, entity_id, agent)
    if body.scope is not None:
        validate_scope(body.scope)
        if not agent.can_access_scope(body.scope):
            raise HTTPException(
                status_code=403,
                detail=f"No write access to scope '{body.scope}'",
            )

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(entity, key, value)
    entity.updated_by = agent.agent_id
    db.commit()
    db.refresh(entity)
    return {"data": EntityOut.model_validate(entity)}


@router.delete("/{entity_id}")
def delete_entity(
    entity_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Read-only token")

    entity = get_scoped_or_404(db, Entity, entity_id, agent)
    entity.deleted_at = int(time.time())
    entity.updated_by = agent.agent_id
    db.commit()
    return {"data": {"id": entity_id, "deleted": True}}
