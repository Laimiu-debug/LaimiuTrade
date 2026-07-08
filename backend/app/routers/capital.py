from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CapitalFlow, Snapshot
from ..services import netvalue, stats

router = APIRouter(prefix="/api/capital", tags=["capital"])


class FlowIn(BaseModel):
    flow_date: date
    kind: str  # initial | deposit | withdraw
    amount: float
    note: str = ""


class SnapshotIn(BaseModel):
    snap_date: date
    total_assets: float
    note: str = ""


@router.get("/flows")
def list_flows(db: Session = Depends(get_db)):
    rows = db.query(CapitalFlow).order_by(CapitalFlow.flow_date.desc(), CapitalFlow.id.desc()).all()
    return [
        {"id": r.id, "flow_date": r.flow_date.isoformat(), "kind": r.kind,
         "amount": r.amount, "note": r.note}
        for r in rows
    ]


@router.post("/flows")
def add_flow(body: FlowIn, db: Session = Depends(get_db)):
    if body.kind not in ("initial", "deposit", "withdraw"):
        raise HTTPException(400, "kind 必须是 initial/deposit/withdraw")
    if body.amount <= 0:
        raise HTTPException(400, "金额必须为正数")
    row = CapitalFlow(flow_date=body.flow_date, kind=body.kind, amount=body.amount, note=body.note)
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.delete("/flows/{flow_id}")
def delete_flow(flow_id: int, db: Session = Depends(get_db)):
    row = db.get(CapitalFlow, flow_id)
    if row is None:
        raise HTTPException(404, "记录不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/snapshots")
def list_snapshots(db: Session = Depends(get_db)):
    rows = db.query(Snapshot).order_by(Snapshot.snap_date.desc()).all()
    return [
        {"id": r.id, "snap_date": r.snap_date.isoformat(),
         "total_assets": r.total_assets, "note": r.note}
        for r in rows
    ]


@router.post("/snapshots")
def upsert_snapshot(body: SnapshotIn, db: Session = Depends(get_db)):
    if body.total_assets < 0:
        raise HTTPException(400, "总资产不能为负")
    row = db.query(Snapshot).filter(Snapshot.snap_date == body.snap_date).first()
    if row is None:
        row = Snapshot(snap_date=body.snap_date, total_assets=body.total_assets, note=body.note)
        db.add(row)
    else:
        row.total_assets = body.total_assets
        row.note = body.note
    db.commit()
    return {"id": row.id}


@router.delete("/snapshots/{snap_id}")
def delete_snapshot(snap_id: int, db: Session = Depends(get_db)):
    row = db.get(Snapshot, snap_id)
    if row is None:
        raise HTTPException(404, "记录不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/nav")
def nav_series(db: Session = Depends(get_db)):
    rate, count = netvalue.node_config(db)
    points = netvalue.build_series(db)
    return {
        "curve": stats.nav_curve(points),
        "state": netvalue.current_state(points, rate, count),
        "max_drawdown_pct": stats.max_drawdown(points),
    }


@router.get("/nodes")
def nodes(db: Session = Depends(get_db)):
    rate, count = netvalue.node_config(db)
    points = netvalue.build_series(db)
    state = netvalue.current_state(points, rate, count)
    events = netvalue.compute_node_events(points, rate, count)
    start_day = points[0].day if points else None
    shares = state["shares"]
    node_list = [
        {
            "level": n,
            "threshold": netvalue.node_threshold(n, rate),
            "assets_equiv": round(netvalue.node_threshold(n, rate) * shares, 2) if shares else None,
            "lit": n in state["lit_levels"],
        }
        for n in range(1, count + 1)
    ]
    return {
        "state": state,
        "nodes": node_list,
        "events": [
            {"level": e["level"], "kind": e["kind"], "date": e["date"].isoformat(),
             "nav": round(e["nav"], 4)}
            for e in events
        ],
        "timing": netvalue.node_timing(events, start_day),
    }
