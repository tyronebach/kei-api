from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from db.connection import get_db
from db.models import Snapshot
from dependencies import AgentPrincipal, get_current_agent, validate_scope
from schemas import SnapshotCreate, SnapshotOut

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("", response_model=list[SnapshotOut])
def list_snapshots(
    scope: str | None = None,
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    q = db.query(Snapshot)
    if scope:
        q = q.filter(Snapshot.scope == scope)
    if from_date:
        q = q.filter(Snapshot.date >= from_date)
    if to_date:
        q = q.filter(Snapshot.date <= to_date)
    q = q.order_by(Snapshot.date.desc())
    return q.offset(offset).limit(limit).all()


@router.get("/latest", response_model=SnapshotOut)
def get_latest_snapshot(
    scope: str = Query("household"),
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    snap = (
        db.query(Snapshot)
        .filter(Snapshot.scope == scope)
        .order_by(Snapshot.date.desc())
        .first()
    )
    if not snap:
        raise HTTPException(status_code=404, detail=f"No snapshots found for scope '{scope}'")
    return snap


@router.get("/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(
    snapshot_id: str,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    snap = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snap


@router.post("", response_model=SnapshotOut, status_code=201)
def create_or_update_snapshot(
    body: SnapshotCreate,
    agent: AgentPrincipal = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    validate_scope(body.scope)
    if not agent.can_write():
        raise HTTPException(status_code=403, detail="Write permission required")

    # Upsert: replace if same scope+date exists
    existing = (
        db.query(Snapshot)
        .filter(Snapshot.scope == body.scope, Snapshot.date == body.date)
        .first()
    )
    if existing:
        existing.data = body.data
        existing.created_by = agent.agent_id
        db.commit()
        db.refresh(existing)
        return existing

    snap = Snapshot(
        scope=body.scope,
        date=body.date,
        data=body.data,
        created_by=agent.agent_id,
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap
