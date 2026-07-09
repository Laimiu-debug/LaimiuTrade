from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CapitalFlow, Snapshot
from ..services import ai as ai_svc
from ..services import capital_estimate as capital_est_svc
from ..services import market as market_svc
from ..services import netvalue, stats

router = APIRouter(prefix="/api/capital", tags=["capital"])


def _parse_money(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").replace("，", "").replace("¥", "").replace("￥", "")
    if not s:
        return None
    if s.endswith("万"):
        try:
            return float(s[:-1]) * 10000
        except ValueError:
            return None
    if s.endswith("亿"):
        try:
            return float(s[:-1]) * 100000000
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_position(p: dict) -> dict:
    if not isinstance(p, dict):
        return {}
    code = str(p.get("code") or "").strip()
    name = str(p.get("name") or "").strip()
    code, name = market_svc.resolve_stock(code, name)
    qty = p.get("qty")
    try:
        qty_val = int(float(qty)) if qty is not None else None
    except (TypeError, ValueError):
        qty_val = None
    price = _parse_money(p.get("price"))
    market_value = _parse_money(p.get("market_value"))
    if market_value is None and qty_val is not None and price is not None:
        market_value = round(qty_val * price, 2)
    return {
        "code": code or None,
        "name": name or None,
        "qty": qty_val,
        "price": price,
        "market_value": market_value,
    }


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

    total_assets = _parse_money(parsed.get("total_assets"))
    available_cash = _parse_money(parsed.get("available_cash"))

    raw_positions = parsed.get("positions") or []
    positions = [_normalize_position(p) for p in raw_positions if isinstance(p, dict)]
    positions = [p for p in positions if p.get("code") or p.get("name")]

    position_value = round(
        sum(p["market_value"] for p in positions if p.get("market_value") is not None),
        2,
    )

    if total_assets is None and positions:
        mv_sum = position_value
        if available_cash is not None:
            mv_sum = round(mv_sum + available_cash, 2)
        if mv_sum > 0:
            total_assets = mv_sum

    return {
        "snap_date": snap_day.isoformat(),
        "total_assets": total_assets,
        "available_cash": available_cash,
        "position_value": position_value if position_value > 0 else None,
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
