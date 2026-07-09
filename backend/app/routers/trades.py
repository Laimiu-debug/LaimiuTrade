from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PendingTrade, Trade
from ..services import ai as ai_svc
from ..services import capital_estimate as capital_est_svc
from ..services import fees as fees_svc
from ..services import rounds as rounds_svc

router = APIRouter(prefix="/api/trades", tags=["trades"])


class TradeIn(BaseModel):
    trade_date: date
    code: str
    name: str = ""
    side: str  # buy | sell
    price: float
    qty: int
    note: str = ""


def _validate(body: TradeIn):
    if body.side not in ("buy", "sell"):
        raise HTTPException(400, "side 必须是 buy/sell")
    if body.price <= 0 or body.qty <= 0:
        raise HTTPException(400, "价格和数量必须为正")


@router.get("")
def list_trades(db: Session = Depends(get_db)):
    rows = db.query(Trade).order_by(Trade.trade_date.desc(), Trade.id.desc()).all()
    return [
        {
            "id": r.id, "trade_date": r.trade_date.isoformat(), "code": r.code,
            "name": r.name, "side": r.side, "price": r.price, "qty": r.qty,
            "fee_commission": r.fee_commission, "fee_stamp": r.fee_stamp,
            "fee_transfer": r.fee_transfer,
            "fees": round(r.fee_commission + r.fee_stamp + r.fee_transfer, 2),
            "amount": round(r.price * r.qty, 2), "note": r.note, "source": r.source,
        }
        for r in rows
    ]


@router.post("")
def add_trade(body: TradeIn, db: Session = Depends(get_db)):
    _validate(body)
    fees = fees_svc.compute_fees(db, body.side, body.price, body.qty)
    row = Trade(
        trade_date=body.trade_date, code=body.code.strip(), name=body.name.strip(),
        side=body.side, price=body.price, qty=body.qty, note=body.note, **fees,
    )
    db.add(row)
    db.commit()
    return {"id": row.id, **fees}


@router.put("/{trade_id}")
def update_trade(trade_id: int, body: TradeIn, db: Session = Depends(get_db)):
    _validate(body)
    row = db.get(Trade, trade_id)
    if row is None:
        raise HTTPException(404, "交易不存在")
    fees = fees_svc.compute_fees(db, body.side, body.price, body.qty)
    row.trade_date = body.trade_date
    row.code = body.code.strip()
    row.name = body.name.strip()
    row.side = body.side
    row.price = body.price
    row.qty = body.qty
    row.note = body.note
    row.fee_commission = fees["fee_commission"]
    row.fee_stamp = fees["fee_stamp"]
    row.fee_transfer = fees["fee_transfer"]
    db.commit()
    return {"ok": True}


@router.delete("/{trade_id}")
def delete_trade(trade_id: int, db: Session = Depends(get_db)):
    row = db.get(Trade, trade_id)
    if row is None:
        raise HTTPException(404, "交易不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/rounds")
def rounds(db: Session = Depends(get_db)):
    result = rounds_svc.build_rounds(db)
    return {"rounds": result, "stats": rounds_svc.round_stats(result)}


# ---------- 截图导入 ----------

@router.post("/import/screenshot")
async def import_screenshot(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    mime = file.content_type or "image/png"
    try:
        items = ai_svc.parse_screenshot(db, content, mime)
    except ai_svc.AIUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"识别失败: {exc}") from exc

    created = 0
    for item in items:
        side = item.get("side")
        if side not in ("buy", "sell"):
            continue  # 持仓行(hold)不能直接变成交易
        try:
            row = PendingTrade(
                trade_date=date.fromisoformat(item["date"]) if item.get("date") else date.today(),
                code=str(item.get("code", "")).strip(),
                name=str(item.get("name", "")).strip(),
                side=side,
                price=float(item.get("price", 0)),
                qty=int(item.get("qty", 0)),
                raw_text=str(item),
            )
        except (ValueError, TypeError):
            continue
        db.add(row)
        created += 1
    db.commit()
    return {"recognized": len(items), "pending_created": created}


@router.get("/pending")
def list_pending(db: Session = Depends(get_db)):
    rows = db.query(PendingTrade).order_by(PendingTrade.id.desc()).all()
    return [
        {
            "id": r.id, "trade_date": r.trade_date.isoformat(), "code": r.code,
            "name": r.name, "side": r.side, "price": r.price, "qty": r.qty,
        }
        for r in rows
    ]


class PendingConfirm(BaseModel):
    trade_date: date
    code: str
    name: str = ""
    side: str
    price: float
    qty: int


def _confirm_pending_row(db: Session, row: PendingTrade, body: PendingConfirm) -> None:
    if body.side not in ("buy", "sell") or body.price <= 0 or body.qty <= 0:
        raise HTTPException(400, "数据不合法")
    fees = fees_svc.compute_fees(db, body.side, body.price, body.qty)
    db.add(Trade(
        trade_date=body.trade_date, code=body.code.strip(), name=body.name.strip(),
        side=body.side, price=body.price, qty=body.qty, source="import", **fees,
    ))
    db.delete(row)


@router.post("/pending/confirm-all")
def confirm_all_pending(db: Session = Depends(get_db)):
    rows = db.query(PendingTrade).order_by(PendingTrade.trade_date, PendingTrade.id).all()
    confirmed = 0
    skipped = 0
    latest_date: date | None = None
    for row in rows:
        if row.side not in ("buy", "sell") or row.price <= 0 or row.qty <= 0 or not row.code.strip():
            skipped += 1
            continue
        body = PendingConfirm(
            trade_date=row.trade_date,
            code=row.code,
            name=row.name,
            side=row.side,
            price=row.price,
            qty=row.qty,
        )
        _confirm_pending_row(db, row, body)
        confirmed += 1
        if latest_date is None or row.trade_date > latest_date:
            latest_date = row.trade_date
    db.commit()

    suggestion = None
    if latest_date is not None and confirmed > 0:
        est = capital_est_svc.estimate_snapshot(db, latest_date)
        if est.get("ok"):
            suggestion = est

    return {"confirmed": confirmed, "skipped": skipped, "snapshot_suggestion": suggestion}


@router.post("/pending/{pending_id}/confirm")
def confirm_pending(pending_id: int, body: PendingConfirm, db: Session = Depends(get_db)):
    row = db.get(PendingTrade, pending_id)
    if row is None:
        raise HTTPException(404, "待确认记录不存在")
    _confirm_pending_row(db, row, body)
    db.commit()
    return {"ok": True}


@router.delete("/pending/{pending_id}")
def delete_pending(pending_id: int, db: Session = Depends(get_db)):
    row = db.get(PendingTrade, pending_id)
    if row is None:
        raise HTTPException(404, "待确认记录不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}
