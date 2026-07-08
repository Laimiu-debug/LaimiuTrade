"""闪记卡片、设置、行情、统计、数据导出。"""

import json
import random
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    CapitalFlow, DailyReview, FlashCard, MonthlyReview, Snapshot, Trade, WeeklyReview,
)
from ..services import market as market_svc
from ..services import netvalue, rounds as rounds_svc
from ..services import settings as settings_svc
from ..services import stats

router = APIRouter(prefix="/api", tags=["misc"])


# ---------- 闪记卡片 ----------

class CardIn(BaseModel):
    content: str
    tags: str = ""


@router.get("/cards")
def list_cards(db: Session = Depends(get_db)):
    rows = db.query(FlashCard).order_by(FlashCard.id.desc()).all()
    return [
        {"id": r.id, "content": r.content, "tags": r.tags,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.post("/cards")
def add_card(body: CardIn, db: Session = Depends(get_db)):
    if not body.content.strip():
        raise HTTPException(400, "内容不能为空")
    row = FlashCard(content=body.content.strip(), tags=body.tags.strip())
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.delete("/cards/{card_id}")
def delete_card(card_id: int, db: Session = Depends(get_db)):
    row = db.get(FlashCard, card_id)
    if row is None:
        raise HTTPException(404, "卡片不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/cards/random")
def random_card(db: Session = Depends(get_db)):
    rows = db.query(FlashCard).all()
    if not rows:
        return None
    # 以当天日期为种子，保证同一天展示同一张
    rng = random.Random(date.today().toordinal())
    r = rng.choice(rows)
    return {"id": r.id, "content": r.content, "tags": r.tags,
            "created_at": r.created_at.isoformat()}


# ---------- 设置 ----------

@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    values = settings_svc.get_all(db)
    if values.get("ai_api_key"):
        values["ai_api_key_set"] = True
        values["ai_api_key"] = ""
    else:
        values["ai_api_key_set"] = False
    return values


class SettingsIn(BaseModel):
    values: dict


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db)):
    values = {k: v for k, v in body.values.items() if k in settings_svc.DEFAULTS}
    # 空 key 表示不修改已保存的 key
    if values.get("ai_api_key") == "":
        values.pop("ai_api_key", None)
    settings_svc.set_many(db, values)
    return {"ok": True}


# ---------- 行情 ----------

@router.get("/market/{code}")
def market_daily(code: str, limit: int = 120, db: Session = Depends(get_db)):
    return market_svc.get_daily(db, code, limit)


# ---------- 统计总览 ----------

@router.get("/stats/overview")
def overview(db: Session = Depends(get_db)):
    points = netvalue.build_series(db)
    rounds = rounds_svc.build_rounds(db)
    events = netvalue.compute_node_events(points)
    start_day = points[0].day if points else None
    return {
        "state": netvalue.current_state(points),
        "curve": stats.nav_curve(points),
        "max_drawdown_pct": stats.max_drawdown(points),
        "weekly_returns": stats.period_returns(points, stats.week_key),
        "monthly_returns": stats.period_returns(points, stats.month_key),
        "round_stats": rounds_svc.round_stats(rounds),
        "node_timing": netvalue.node_timing(events, start_day),
        "missing_reviews": stats.missing_reviews(db),
    }


# ---------- 导出 ----------

@router.get("/export/json")
def export_json(db: Session = Depends(get_db)):
    def rows(model):
        return [
            {c.name: (v.isoformat() if hasattr(v := getattr(r, c.name), "isoformat") else v)
             for c in model.__table__.columns}
            for r in db.query(model).all()
        ]

    payload = {
        "exported_at": date.today().isoformat(),
        "capital_flows": rows(CapitalFlow),
        "snapshots": rows(Snapshot),
        "trades": rows(Trade),
        "daily_reviews": rows(DailyReview),
        "weekly_reviews": rows(WeeklyReview),
        "monthly_reviews": rows(MonthlyReview),
        "flash_cards": rows(FlashCard),
    }
    return JSONResponse(
        payload,
        headers={"Content-Disposition": f"attachment; filename=laimiutrade-backup-{date.today().isoformat()}.json"},
    )


@router.get("/export/markdown")
def export_markdown(db: Session = Depends(get_db)):
    lines = [f"# LaimiuTrade 复盘导出（{date.today().isoformat()}）", ""]
    reviews = db.query(DailyReview).order_by(DailyReview.review_date).all()
    for r in reviews:
        lines += [f"## {r.review_date.isoformat()} 每日复盘", ""]
        if r.market_observation:
            lines += ["### 盘面观察", r.market_observation, ""]
        if r.decision_review:
            lines += ["### 决策复盘", r.decision_review, ""]
        if r.mistakes:
            lines += ["### 错误教训", r.mistakes, ""]
        scores = json.loads(r.scores or "{}")
        if scores:
            lines.append("### 打分")
            for dim, item in scores.items():
                final = item.get("final")
                comment = item.get("comment", "")
                lines.append(f"- {dim}: {final if final is not None else '-'} {comment}")
            lines.append("")
        if r.next_market_forecast or r.next_position_plan:
            lines += ["### 次日预研",
                      f"大盘预判：{r.next_market_forecast}",
                      f"仓位计划：{r.next_position_plan}",
                      f"风险预案：{r.next_risk_plan}", ""]
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=laimiutrade-reviews-{date.today().isoformat()}.md"},
    )
