import json
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import UPLOAD_DIR, get_db
from ..models import DailyReview, MonthlyReview, Snapshot, Trade, WeeklyReview
from ..services import ai as ai_svc
from ..services import netvalue, rounds as rounds_svc, stats

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def _daily_dict(r: DailyReview) -> dict:
    return {
        "review_date": r.review_date.isoformat(),
        "market_observation": r.market_observation,
        "decision_review": r.decision_review,
        "mistakes": r.mistakes,
        "images": json.loads(r.images or "[]"),
        "scores": json.loads(r.scores or "{}"),
        "ai_summary": r.ai_summary,
        "next_market_forecast": r.next_market_forecast,
        "next_watchlist": json.loads(r.next_watchlist or "[]"),
        "next_position_plan": r.next_position_plan,
        "next_risk_plan": r.next_risk_plan,
    }


def _get_or_create_daily(db: Session, day: date) -> DailyReview:
    row = db.query(DailyReview).filter(DailyReview.review_date == day).first()
    if row is None:
        row = DailyReview(review_date=day)
        db.add(row)
        db.commit()
    return row


@router.get("/daily/{day}")
def get_daily(day: date, db: Session = Depends(get_db)):
    row = db.query(DailyReview).filter(DailyReview.review_date == day).first()
    data = _daily_dict(row) if row else _daily_dict(DailyReview(review_date=day))
    trades = db.query(Trade).filter(Trade.trade_date == day).order_by(Trade.id).all()
    data["trades"] = [
        {"id": t.id, "code": t.code, "name": t.name, "side": t.side,
         "price": t.price, "qty": t.qty,
         "fees": round(t.fee_commission + t.fee_stamp + t.fee_transfer, 2)}
        for t in trades
    ]
    snap = db.query(Snapshot).filter(Snapshot.snap_date == day).first()
    data["snapshot"] = snap.total_assets if snap else None
    return data


class DailyIn(BaseModel):
    market_observation: str = ""
    decision_review: str = ""
    mistakes: str = ""
    scores: dict = {}
    next_market_forecast: str = ""
    next_watchlist: list = []
    next_position_plan: str = ""
    next_risk_plan: str = ""


@router.put("/daily/{day}")
def save_daily(day: date, body: DailyIn, db: Session = Depends(get_db)):
    row = _get_or_create_daily(db, day)
    row.market_observation = body.market_observation
    row.decision_review = body.decision_review
    row.mistakes = body.mistakes
    row.scores = json.dumps(body.scores, ensure_ascii=False)
    row.next_market_forecast = body.next_market_forecast
    row.next_watchlist = json.dumps(body.next_watchlist, ensure_ascii=False)
    row.next_position_plan = body.next_position_plan
    row.next_risk_plan = body.next_risk_plan
    db.commit()
    return {"ok": True}


@router.post("/daily/{day}/images")
async def upload_image(day: date, file: UploadFile = File(...), db: Session = Depends(get_db)):
    ext = (file.filename or "img.png").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "gif", "webp"):
        raise HTTPException(400, "仅支持图片文件")
    fname = f"{day.isoformat()}-{uuid.uuid4().hex[:8]}.{ext}"
    (UPLOAD_DIR / fname).write_bytes(await file.read())
    row = _get_or_create_daily(db, day)
    images = json.loads(row.images or "[]")
    images.append(f"/uploads/{fname}")
    row.images = json.dumps(images)
    db.commit()
    return {"url": f"/uploads/{fname}"}


@router.delete("/daily/{day}/images")
def remove_image(day: date, url: str, db: Session = Depends(get_db)):
    row = _get_or_create_daily(db, day)
    images = json.loads(row.images or "[]")
    if url in images:
        images.remove(url)
        row.images = json.dumps(images)
        db.commit()
        target = UPLOAD_DIR / url.split("/")[-1]
        if target.exists():
            target.unlink()
    return {"ok": True}


@router.post("/daily/{day}/ai-score")
def ai_score(day: date, db: Session = Depends(get_db)):
    row = _get_or_create_daily(db, day)
    prev = (
        db.query(DailyReview)
        .filter(DailyReview.review_date < day)
        .order_by(DailyReview.review_date.desc())
        .first()
    )
    plan = ""
    if prev:
        plan_parts = [prev.next_market_forecast, prev.next_position_plan, prev.next_risk_plan]
        watchlist = json.loads(prev.next_watchlist or "[]")
        if watchlist:
            plan_parts.append("关注标的: " + "; ".join(
                f"{w.get('name', '')}({w.get('code', '')}) {w.get('condition', '')} -> {w.get('action', '')}"
                for w in watchlist
            ))
        plan = "\n".join(p for p in plan_parts if p)
    try:
        result = ai_svc.score_review(db, day, {
            "market_observation": row.market_observation,
            "decision_review": row.decision_review,
            "mistakes": row.mistakes,
            "plan": plan,
        })
    except ai_svc.AIUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 打分失败: {exc}") from exc

    scores = json.loads(row.scores or "{}")
    for dim, item in (result.get("scores") or {}).items():
        if dim not in ai_svc.SCORE_DIMENSIONS:
            continue
        entry = scores.get(dim) or {}
        entry["ai"] = item.get("score")
        entry["comment"] = item.get("comment", "")
        if entry.get("final") is None:
            entry["final"] = item.get("score")
        scores[dim] = entry
    row.scores = json.dumps(scores, ensure_ascii=False)
    row.ai_summary = result.get("summary", "")
    db.commit()
    return {"scores": scores, "summary": row.ai_summary}


@router.get("/daily")
def list_daily(db: Session = Depends(get_db)):
    rows = db.query(DailyReview).order_by(DailyReview.review_date.desc()).all()
    return [r.review_date.isoformat() for r in rows]


@router.get("/missing")
def missing(db: Session = Depends(get_db)):
    return stats.missing_reviews(db)


# ---------- 周/月复盘 ----------

def _week_range(year: int, week: int) -> tuple[date, date]:
    start = date.fromisocalendar(year, week, 1)
    return start, start + timedelta(days=6)


def _period_auto(db: Session, start: date, end: date) -> dict:
    points = netvalue.build_series(db)
    in_range = [p for p in points if start <= p.day <= end]
    before = [p for p in points if p.day < start]
    start_nav = before[-1].nav if before else (in_range[0].nav if in_range else 1.0)
    end_nav = in_range[-1].nav if in_range else start_nav
    ret = (end_nav / start_nav - 1) * 100 if start_nav > 0 else 0.0

    peak = start_nav
    mdd = 0.0
    for p in in_range:
        peak = max(peak, p.nav)
        if peak > 0:
            mdd = min(mdd, (p.nav / peak - 1) * 100)

    all_rounds = rounds_svc.build_rounds(db)
    closed_in = [
        r for r in all_rounds
        if r["status"] == "closed" and r["end_date"] and start.isoformat() <= r["end_date"] <= end.isoformat()
    ]
    trade_count = db.query(Trade).filter(Trade.trade_date >= start, Trade.trade_date <= end).count()
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "return_pct": round(ret, 2),
        "max_drawdown_pct": round(mdd, 2),
        "end_nav": round(end_nav, 4),
        "trade_count": trade_count,
        "closed_rounds": len(closed_in),
        "round_pnl": round(sum(r["pnl"] or 0 for r in closed_in), 2),
        "win_rounds": len([r for r in closed_in if (r["pnl"] or 0) > 0]),
    }


class WeeklyIn(BaseModel):
    right_things: str = ""
    wrong_things: str = ""
    next_strategy: str = ""


@router.get("/weekly/{year}/{week}")
def get_weekly(year: int, week: int, db: Session = Depends(get_db)):
    row = db.query(WeeklyReview).filter_by(year=year, week=week).first()
    start, end = _week_range(year, week)
    return {
        "year": year, "week": week,
        "right_things": row.right_things if row else "",
        "wrong_things": row.wrong_things if row else "",
        "next_strategy": row.next_strategy if row else "",
        "auto": _period_auto(db, start, end),
    }


@router.put("/weekly/{year}/{week}")
def save_weekly(year: int, week: int, body: WeeklyIn, db: Session = Depends(get_db)):
    row = db.query(WeeklyReview).filter_by(year=year, week=week).first()
    if row is None:
        row = WeeklyReview(year=year, week=week)
        db.add(row)
    row.right_things = body.right_things
    row.wrong_things = body.wrong_things
    row.next_strategy = body.next_strategy
    db.commit()
    return {"ok": True}


class MonthlyIn(BaseModel):
    system_iteration: str = ""
    next_goal: str = ""


@router.get("/monthly/{year}/{month}")
def get_monthly(year: int, month: int, db: Session = Depends(get_db)):
    row = db.query(MonthlyReview).filter_by(year=year, month=month).first()
    start = date(year, month, 1)
    end = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    points = netvalue.build_series(db)
    state = netvalue.current_state(points)
    return {
        "year": year, "month": month,
        "system_iteration": row.system_iteration if row else "",
        "next_goal": row.next_goal if row else "",
        "auto": _period_auto(db, start, end),
        "node_state": {"lit_count": state["lit_count"], "nav": state["nav"]},
    }


@router.put("/monthly/{year}/{month}")
def save_monthly(year: int, month: int, body: MonthlyIn, db: Session = Depends(get_db)):
    row = db.query(MonthlyReview).filter_by(year=year, month=month).first()
    if row is None:
        row = MonthlyReview(year=year, month=month)
        db.add(row)
    row.system_iteration = body.system_iteration
    row.next_goal = body.next_goal
    db.commit()
    return {"ok": True}
