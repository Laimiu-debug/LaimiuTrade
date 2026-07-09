from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CapitalFlow, Snapshot
from ..services import ai as ai_svc
from ..services import capital_estimate as capital_est_svc
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


@router.get("/estimate")
def estimate_assets(day: date = Query(..., alias="date"), db: Session = Depends(get_db)):
    """根据出入金与交易流水，估算某日收盘总资产。"""
    return capital_est_svc.estimate_snapshot(db, day)


@router.post("/import/screenshot")
async def import_account_screenshot(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """识别持仓/资产截图，返回总资产与持仓明细供确认。"""
    content = await file.read()
    mime = file.content_type or "image/png"
    try:
        parsed = ai_svc.parse_account_screenshot(db, content, mime)
    except ai_svc.AIUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"识别失败: {exc}") from exc

    snap_date = parsed.get("snap_date")
    if isinstance(snap_date, str) and snap_date:
        try:
            snap_day = date.fromisoformat(snap_date[:10])
        except ValueError:
            snap_day = date.today()
    else:
        snap_day = date.today()

    total_assets = parsed.get("total_assets")
    if total_assets is not None:
        try:
            total_assets = float(total_assets)
        except (TypeError, ValueError):
            total_assets = None

    positions = parsed.get("positions") or []
    if total_assets is None and positions:
        mv_sum = 0.0
        for p in positions:
            if not isinstance(p, dict):
                continue
            mv = p.get("market_value")
            if mv is not None:
                try:
                    mv_sum += float(mv)
                except (TypeError, ValueError):
                    pass
        cash = parsed.get("available_cash")
        if cash is not None:
            try:
                mv_sum += float(cash)
            except (TypeError, ValueError):
                pass
        if mv_sum > 0:
            total_assets = round(mv_sum, 2)

    return {
        "snap_date": snap_day.isoformat(),
        "total_assets": total_assets,
        "available_cash": parsed.get("available_cash"),
        "positions": positions,
        "recognized": len(positions) + (1 if total_assets is not None else 0),
    }


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
