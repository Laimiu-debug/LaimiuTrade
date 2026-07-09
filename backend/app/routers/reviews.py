import json
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import UPLOAD_DIR, get_db
from ..models import DailyReview, MonthlyReview, Snapshot, Trade, WeeklyReview
from ..services import ai as ai_svc
from ..services import market as market_svc
from ..services import netvalue, rounds as rounds_svc, stats

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

_DIM_ALIASES = {
    "仓位控制": "position",
    "回撤控制": "drawdown",
    "计划执行力": "discipline",
    "买点质量": "entry",
    "卖点质量": "exit",
    "情绪管理": "emotion",
}


def _coerce_trade_id(raw, fallback: int | None = None) -> int | None:
    if raw is None:
        return fallback
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    s = str(raw).strip().lstrip("#")
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits:
        return int(digits)
    return fallback


def _normalize_dim_scores(scores: dict | None) -> dict:
    if not isinstance(scores, dict):
        return {}
    out: dict = {}
    for key, val in scores.items():
        dim = key if key in ai_svc.SCORE_DIMENSIONS else _DIM_ALIASES.get(str(key))
        if not dim:
            continue
        if isinstance(val, (int, float)):
            out[dim] = {"score": int(val), "comment": ""}
        elif isinstance(val, dict):
            score_raw = val.get("score", val.get("分数", val.get("value")))
            try:
                score_val = int(score_raw) if score_raw is not None else None
            except (TypeError, ValueError):
                score_val = None
            comment = val.get("comment") or val.get("点评") or val.get("commentary") or ""
            out[dim] = {"score": score_val, "comment": str(comment) if comment else ""}
    return out


def _normalize_ai_trade_items(result: dict, expected_ids: list[int] | None) -> list[dict]:
    """兼容 LLM 多种 JSON 结构，并修正 id / scores 字段。"""
    items = result.get("trades")
    if items is None and isinstance(result.get("data"), dict):
        items = result["data"].get("trades")
    if isinstance(items, dict):
        items = [
            {"id": key, **val} if isinstance(val, dict) else {"id": key, "summary": val}
            for key, val in items.items()
        ]
    if not isinstance(items, list):
        items = []

    expected = list(expected_ids or [])
    normalized: list[dict] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        fallback = expected[i] if i < len(expected) else (expected[0] if len(expected) == 1 else None)
        trade_id = _coerce_trade_id(item.get("id"), fallback)
        if trade_id is None:
            continue
        summary = item.get("summary") or item.get("总评") or item.get("comment") or ""
        normalized.append({
            "id": trade_id,
            "summary": summary,
            "scores": _normalize_dim_scores(item.get("scores")),
        })

    # 单笔分析时 LLM 常漏 id：若仅一条结果且仅一笔待评，强制对齐
    if not normalized and len(expected) == 1 and len(items) == 1 and isinstance(items[0], dict):
        item = items[0]
        normalized.append({
            "id": expected[0],
            "summary": item.get("summary") or item.get("总评") or "",
            "scores": _normalize_dim_scores(item.get("scores")),
        })
    # LLM 有时直接返回扁平结构，无 trades 数组
    if not normalized and len(expected) == 1:
        flat_scores = _normalize_dim_scores({
            k: v for k, v in result.items()
            if k in ai_svc.SCORE_DIMENSIONS or k in _DIM_ALIASES
        })
        summary = result.get("summary") or result.get("daily_summary") or result.get("总评") or ""
        if flat_scores or (isinstance(summary, str) and summary.strip()):
            normalized.append({
                "id": expected[0],
                "summary": summary,
                "scores": flat_scores,
            })
    return normalized


def _merge_trade_score_items(
    trade_scores: dict,
    items: list,
    expected_ids: list[int] | None = None,
) -> int:
    merged = 0
    if expected_ids and not items:
        items = []
    for item in items:
        trade_id = _coerce_trade_id(item.get("id"))
        if trade_id is None:
            continue
        key = str(trade_id)
        entry: dict = trade_scores.get(key) or {}
        summary = item.get("summary")
        if isinstance(summary, str) and summary.strip():
            entry["_summary"] = {"comment": summary.strip()}
        for dim, val in _normalize_dim_scores(item.get("scores")).items():
            dim_entry = entry.get(dim) or {}
            score_raw = val.get("score")
            if score_raw is not None:
                try:
                    dim_entry["ai"] = int(score_raw)
                except (TypeError, ValueError):
                    pass
            dim_entry["comment"] = val.get("comment", "")
            if dim_entry.get("final") is None and dim_entry.get("ai") is not None:
                dim_entry["final"] = dim_entry["ai"]
            entry[dim] = dim_entry
        trade_scores[key] = entry
        if (isinstance(summary, str) and summary.strip()) or any(
            isinstance(entry.get(dim), dict) and entry[dim].get("ai") is not None
            for dim in ai_svc.SCORE_DIMENSIONS
        ):
            merged += 1
    return merged


def _aggregate_daily_scores(trade_scores: dict) -> dict:
    """从已打分交易汇总整日 6 维度概览（仅均分，维度点评留空由用户或整日总评补充）。"""
    daily: dict = {}
    for dim in ai_svc.SCORE_DIMENSIONS:
        collected: list[dict] = []
        for key, entry in trade_scores.items():
            if not isinstance(entry, dict) or str(key).startswith("g:"):
                continue
            dim_entry = entry.get(dim)
            if isinstance(dim_entry, dict) and dim_entry.get("ai") is not None:
                collected.append(dim_entry)
        if not collected:
            continue
        avg = round(sum(d["ai"] for d in collected if d.get("ai") is not None) / len(collected))
        daily[dim] = {
            "ai": avg,
            "final": avg,
            "comment": "",
        }
    return daily


def _detect_t_groups(trades: list[Trade]) -> list[dict]:
    by_code: dict[str, list[Trade]] = {}
    for t in trades:
        by_code.setdefault(t.code, []).append(t)
    groups: list[dict] = []
    for code, items in by_code.items():
        sides = {t.side for t in items}
        if "buy" in sides and "sell" in sides and len(items) >= 2:
            groups.append({
                "id": f"t:{code}",
                "code": code,
                "name": items[0].name or code,
                "kind": "t",
                "trade_ids": [t.id for t in items],
            })
    return groups


def _group_score_key(code: str) -> str:
    return f"g:{code}"


def _merge_group_score(trade_scores: dict, code: str, trade_ids: list[int], result: dict) -> None:
    key = _group_score_key(code)
    entry: dict = trade_scores.get(key) or {}
    summary = result.get("group_summary") or result.get("daily_summary")
    if isinstance(summary, str) and summary.strip():
        entry["_summary"] = {"comment": summary.strip()}
    entry["_meta"] = {"kind": "t", "code": code, "trade_ids": trade_ids}
    for dim, val in _normalize_dim_scores(result.get("group_scores")).items():
        dim_entry = entry.get(dim) or {}
        score_raw = val.get("score")
        if score_raw is not None:
            try:
                dim_entry["ai"] = int(score_raw)
            except (TypeError, ValueError):
                pass
        dim_entry["comment"] = val.get("comment", "")
        if dim_entry.get("final") is None and dim_entry.get("ai") is not None:
            dim_entry["final"] = dim_entry["ai"]
        entry[dim] = dim_entry
    trade_scores[key] = entry


def _build_trade_summaries_text(db: Session, day: date, trade_scores: dict) -> str:
    """从已保存的逐笔评分生成可读的整日 AI 总评。"""
    trades = db.query(Trade).filter(Trade.trade_date == day).order_by(Trade.id).all()
    lines: list[str] = []
    for t in trades:
        entry = trade_scores.get(str(t.id))
        if not isinstance(entry, dict):
            continue
        summary_obj = entry.get("_summary")
        summary = summary_obj.get("comment", "").strip() if isinstance(summary_obj, dict) else ""
        if not summary:
            continue
        side = "买入" if t.side == "buy" else "卖出"
        label = t.name or t.code
        lines.append(f"· {side} {label}({t.code})：{summary}")
    return "\n".join(lines)


def _plan_from_prev(db: Session, day: date) -> str:
    prev = (
        db.query(DailyReview)
        .filter(DailyReview.review_date < day)
        .order_by(DailyReview.review_date.desc())
        .first()
    )
    if not prev:
        return ""
    plan_parts = [prev.next_market_forecast, prev.next_position_plan, prev.next_risk_plan]
    watchlist = json.loads(prev.next_watchlist or "[]")
    if watchlist:
        plan_parts.append("关注标的: " + "; ".join(
            f"{w.get('name', '')}({w.get('code', '')}) {w.get('condition', '')} -> {w.get('action', '')}"
            for w in watchlist
        ))
    return "\n".join(p for p in plan_parts if p)


def _run_ai_score(db: Session, row: DailyReview, day: date, trade_ids: list[int] | None) -> dict:
    try:
        result = ai_svc.score_trades(db, day, {
            "market_observation": row.market_observation,
            "decision_review": row.decision_review,
            "mistakes": row.mistakes,
            "plan": _plan_from_prev(db, day),
        }, trade_ids=trade_ids)
    except ai_svc.AIUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 打分失败: {exc}") from exc

    trade_scores = json.loads(row.trade_scores or "{}")
    items = _normalize_ai_trade_items(result, trade_ids)
    merged = _merge_trade_score_items(trade_scores, items, trade_ids)
    if trade_ids and merged == 0:
        raise HTTPException(502, "AI 未返回有效的逐笔评分，请重试")
    scores = _aggregate_daily_scores(trade_scores)

    if trade_ids is None and result.get("daily_summary"):
        row.ai_summary = result.get("daily_summary", "")
    elif isinstance(result.get("daily_summary"), str) and result.get("daily_summary", "").strip():
        row.ai_summary = result.get("daily_summary", "").strip()
    else:
        built = _build_trade_summaries_text(db, day, trade_scores)
        if built:
            row.ai_summary = built

    row.trade_scores = json.dumps(trade_scores, ensure_ascii=False)
    row.scores = json.dumps(scores, ensure_ascii=False)
    db.commit()
    return {
        "trade_scores": trade_scores,
        "scores": scores,
        "summary": row.ai_summary,
        "merged_count": merged,
    }


def _run_ai_score_t_group(db: Session, row: DailyReview, day: date, code: str, trade_ids: list[int]) -> dict:
    try:
        result = ai_svc.score_t_group(db, day, {
            "market_observation": row.market_observation,
            "decision_review": row.decision_review,
            "mistakes": row.mistakes,
            "plan": _plan_from_prev(db, day),
        }, trade_ids=trade_ids)
    except ai_svc.AIUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"做T AI 打分失败: {exc}") from exc

    trade_scores = json.loads(row.trade_scores or "{}")
    _merge_group_score(trade_scores, code, trade_ids, result)
    items = _normalize_ai_trade_items(result, trade_ids)
    merged = _merge_trade_score_items(trade_scores, items, trade_ids)
    scores = _aggregate_daily_scores(trade_scores)
    built = _build_trade_summaries_text(db, day, trade_scores)
    group_summary = result.get("group_summary") or result.get("daily_summary") or ""
    if isinstance(group_summary, str) and group_summary.strip():
        prefix = f"【做T·{code}】{group_summary.strip()}"
        row.ai_summary = prefix if not built else f"{prefix}\n{built}"
    elif built:
        row.ai_summary = built

    row.trade_scores = json.dumps(trade_scores, ensure_ascii=False)
    row.scores = json.dumps(scores, ensure_ascii=False)
    db.commit()
    return {
        "trade_scores": trade_scores,
        "scores": scores,
        "summary": row.ai_summary,
        "merged_count": merged,
    }


def _daily_dict(r: DailyReview) -> dict:
    return {
        "review_date": r.review_date.isoformat(),
        "market_observation": r.market_observation,
        "decision_review": r.decision_review,
        "mistakes": r.mistakes,
        "images": json.loads(r.images or "[]"),
        "scores": json.loads(r.scores or "{}"),
        "trade_scores": json.loads(getattr(r, "trade_scores", None) or "{}"),
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
    if "trade_scores" not in data:
        data["trade_scores"] = {}
    trades = db.query(Trade).filter(Trade.trade_date == day).order_by(Trade.id).all()
    data["trades"] = [
        {"id": t.id, "code": t.code, "name": t.name, "side": t.side,
         "price": t.price, "qty": t.qty,
         "fees": round(t.fee_commission + t.fee_stamp + t.fee_transfer, 2)}
        for t in trades
    ]
    data["t_groups"] = _detect_t_groups(trades)
    snap = db.query(Snapshot).filter(Snapshot.snap_date == day).first()
    if snap:
        positions = json.loads(snap.positions or "[]")
        if not isinstance(positions, list):
            positions = []
        data["snapshot"] = {
            "total_assets": snap.total_assets,
            "available_cash": snap.available_cash,
            "position_value": snap.position_value,
            "positions": positions,
        }
    else:
        data["snapshot"] = None
    return data


class DailyIn(BaseModel):
    market_observation: str = ""
    decision_review: str = ""
    mistakes: str = ""
    scores: dict | None = None
    trade_scores: dict | None = None
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
    if body.scores is not None:
        row.scores = json.dumps(body.scores, ensure_ascii=False)
    if body.trade_scores is not None:
        row.trade_scores = json.dumps(body.trade_scores, ensure_ascii=False)
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
    return _run_ai_score(db, row, day, trade_ids=None)


class AiScoreIn(BaseModel):
    trade_ids: list[int] = []


@router.post("/daily/{day}/ai-score/batch")
def ai_score_batch(day: date, body: AiScoreIn, db: Session = Depends(get_db)):
    row = _get_or_create_daily(db, day)
    if not body.trade_ids:
        raise HTTPException(400, "请指定要分析的交易")
    return _run_ai_score(db, row, day, trade_ids=body.trade_ids)


class TGroupScoreIn(BaseModel):
    code: str
    trade_ids: list[int] = []


@router.post("/daily/{day}/ai-score/t-group")
def ai_score_t_group(day: date, body: TGroupScoreIn, db: Session = Depends(get_db)):
    row = _get_or_create_daily(db, day)
    if not body.trade_ids:
        raise HTTPException(400, "请指定做T涉及的交易")
    trades = db.query(Trade).filter(Trade.id.in_(body.trade_ids), Trade.trade_date == day).all()
    if len(trades) != len(set(body.trade_ids)):
        raise HTTPException(404, "部分交易不存在或不属于该日")
    code = body.code.strip()
    if any(t.code != code for t in trades):
        raise HTTPException(400, "做T交易代码不一致")
    return _run_ai_score_t_group(db, row, day, code, body.trade_ids)


@router.post("/daily/{day}/ai-score/{trade_id}")
def ai_score_one(day: date, trade_id: int, db: Session = Depends(get_db)):
    trade = db.get(Trade, trade_id)
    if trade is None or trade.trade_date != day:
        raise HTTPException(404, "交易不存在或不属于该日")
    row = _get_or_create_daily(db, day)
    return _run_ai_score(db, row, day, trade_ids=[trade_id])


@router.post("/daily/{day}/ai-review")
def ai_review(day: date, db: Session = Depends(get_db)):
    row = _get_or_create_daily(db, day)
    try:
        result = ai_svc.generate_daily_review(db, day, {
            "market_observation": row.market_observation,
            "decision_review": row.decision_review,
            "mistakes": row.mistakes,
        })
    except ai_svc.AIUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 复盘失败: {exc}") from exc

    for field in ("market_observation", "decision_review", "mistakes",
                  "next_market_forecast", "next_position_plan", "next_risk_plan"):
        val = result.get(field)
        if isinstance(val, str) and val.strip():
            setattr(row, field, val.strip())
    db.commit()
    return {
        "market_observation": row.market_observation,
        "decision_review": row.decision_review,
        "mistakes": row.mistakes,
        "next_market_forecast": row.next_market_forecast,
        "next_position_plan": row.next_position_plan,
        "next_risk_plan": row.next_risk_plan,
    }


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


def _build_period_context(db: Session, start: date, end: date) -> dict:
    trades = (
        db.query(Trade)
        .filter(Trade.trade_date >= start, Trade.trade_date <= end)
        .order_by(Trade.trade_date, Trade.id)
        .all()
    )
    trade_lines = [
        f"{t.trade_date} {'买入' if t.side == 'buy' else '卖出'} {t.name or t.code}({t.code}) "
        f"{t.qty}股 @ {t.price}"
        for t in trades
    ]

    daily_rows = (
        db.query(DailyReview)
        .filter(DailyReview.review_date >= start, DailyReview.review_date <= end)
        .order_by(DailyReview.review_date)
        .all()
    )
    daily_excerpts: list[str] = []
    for row in daily_rows:
        parts: list[str] = []
        if row.market_observation.strip():
            parts.append(f"观察:{row.market_observation.strip()[:100]}")
        if row.decision_review.strip():
            parts.append(f"决策:{row.decision_review.strip()[:100]}")
        if row.mistakes.strip():
            parts.append(f"教训:{row.mistakes.strip()[:100]}")
        if row.ai_summary.strip():
            parts.append(f"总评:{row.ai_summary.strip()[:100]}")
        if parts:
            daily_excerpts.append(f"{row.review_date}: " + " | ".join(parts))

    weekly_excerpts: list[str] = []
    for wrow in db.query(WeeklyReview).all():
        w_start, w_end = _week_range(wrow.year, wrow.week)
        if w_start > end or w_end < start:
            continue
        chunks = [wrow.right_things.strip(), wrow.wrong_things.strip(), wrow.next_strategy.strip()]
        if any(chunks):
            weekly_excerpts.append(
                f"{wrow.year}W{wrow.week}: "
                f"对={wrow.right_things.strip()[:80] or '—'} | "
                f"错={wrow.wrong_things.strip()[:80] or '—'}"
            )

    all_rounds = rounds_svc.build_rounds(db)
    closed_in = [
        r for r in all_rounds
        if r["status"] == "closed" and r["end_date"] and start.isoformat() <= r["end_date"] <= end.isoformat()
    ]
    round_lines = [
        f"{r['name']}({r['code']}) {r['start_date']}→{r['end_date']} "
        f"盈亏 {r['pnl']}元 ({r['pnl_pct']}%)"
        for r in closed_in
    ]

    codes = sorted({t.code for t in trades})
    market_text = market_svc.market_context_text(db, ["000001.SH", "399001.SZ", *codes[:5]], end)

    return {
        "trade_lines": trade_lines,
        "daily_excerpts": daily_excerpts,
        "weekly_excerpts": weekly_excerpts,
        "round_lines": round_lines,
        "market_text": market_text,
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


@router.post("/weekly/{year}/{week}/ai-review")
def ai_weekly_review(year: int, week: int, db: Session = Depends(get_db)):
    row = db.query(WeeklyReview).filter_by(year=year, week=week).first()
    if row is None:
        row = WeeklyReview(year=year, week=week)
        db.add(row)
        db.flush()
    start, end = _week_range(year, week)
    auto = _period_auto(db, start, end)
    context = _build_period_context(db, start, end)
    try:
        result = ai_svc.generate_weekly_review(db, year, week, start, end, auto, context, {
            "right_things": row.right_things,
            "wrong_things": row.wrong_things,
            "next_strategy": row.next_strategy,
        })
    except ai_svc.AIUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 周复盘失败: {exc}") from exc

    for field in ("right_things", "wrong_things", "next_strategy"):
        val = result.get(field)
        if isinstance(val, str) and val.strip():
            setattr(row, field, val.strip())
    db.commit()
    return {
        "right_things": row.right_things,
        "wrong_things": row.wrong_things,
        "next_strategy": row.next_strategy,
    }


class MonthlyIn(BaseModel):
    system_iteration: str = ""
    next_goal: str = ""


@router.get("/monthly/{year}/{month}")
def get_monthly(year: int, month: int, db: Session = Depends(get_db)):
    row = db.query(MonthlyReview).filter_by(year=year, month=month).first()
    start = date(year, month, 1)
    end = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    rate, count = netvalue.node_config(db)
    points = netvalue.build_series(db)
    state = netvalue.current_state(points, rate, count)
    return {
        "year": year, "month": month,
        "system_iteration": row.system_iteration if row else "",
        "next_goal": row.next_goal if row else "",
        "auto": _period_auto(db, start, end),
        "node_state": {
            "lit_count": state["lit_count"],
            "node_count": state["node_count"],
            "nav": state["nav"],
        },
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


@router.post("/monthly/{year}/{month}/ai-review")
def ai_monthly_review(year: int, month: int, db: Session = Depends(get_db)):
    row = db.query(MonthlyReview).filter_by(year=year, month=month).first()
    if row is None:
        row = MonthlyReview(year=year, month=month)
        db.add(row)
        db.flush()
    start = date(year, month, 1)
    end = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    auto = _period_auto(db, start, end)
    context = _build_period_context(db, start, end)
    rate, count = netvalue.node_config(db)
    points = netvalue.build_series(db)
    state = netvalue.current_state(points, rate, count)
    node_state = {
        "lit_count": state["lit_count"],
        "node_count": state["node_count"],
        "nav": state["nav"],
    }
    try:
        result = ai_svc.generate_monthly_review(
            db, year, month, start, end, auto, node_state, context, {
                "system_iteration": row.system_iteration,
                "next_goal": row.next_goal,
            },
        )
    except ai_svc.AIUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"AI 月复盘失败: {exc}") from exc

    for field in ("system_iteration", "next_goal"):
        val = result.get(field)
        if isinstance(val, str) and val.strip():
            setattr(row, field, val.strip())
    db.commit()
    return {
        "system_iteration": row.system_iteration,
        "next_goal": row.next_goal,
    }
