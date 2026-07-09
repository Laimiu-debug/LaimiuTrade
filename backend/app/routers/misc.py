"""闪记卡片、设置、行情、统计、数据导出。"""

import json
import os
import random
import shutil
import sys
import threading
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import DATA_DIR, ROOT_DIR, engine, get_db
from ..models import (
    CapitalFlow, DailyReview, FlashCard, MonthlyReview, Snapshot, Trade, WeeklyReview,
)
from ..services import ai as ai_svc
from ..services import folder_dialog
from ..services import market as market_svc
from ..services import netvalue, rounds as rounds_svc
from ..services import settings as settings_svc
from ..services import stats

router = APIRouter(prefix="/api", tags=["misc"])


# ---------- 系统 ----------

@router.post("/system/shutdown")
def shutdown():
    """退出整个程序（响应发出后延迟终止进程）。"""
    threading.Timer(0.4, os._exit, args=(0,)).start()
    return {"ok": True}


class MoveDataIn(BaseModel):
    target_dir: str


DATA_SUBDIR = "TradingMS-data"


def _resolve_migration_target(raw: str) -> tuple[Path, str]:
    """解析迁移目标：空目录直接用，非空目录自动使用子文件夹。"""
    base = Path(raw).expanduser().resolve()
    if base == DATA_DIR.resolve():
        raise HTTPException(400, "目标目录与当前数据目录相同")
    if base == ROOT_DIR.resolve():
        raise HTTPException(400, "不能使用程序根目录作为数据目录")

    if not base.exists():
        return base, "将创建新目录"

    if not any(base.iterdir()):
        return base, "使用所选空目录"

    sub = base / DATA_SUBDIR
    if sub.exists() and any(sub.iterdir()):
        if sub.resolve() == DATA_DIR.resolve():
            raise HTTPException(400, "该位置已是当前数据目录")
        raise HTTPException(
            400,
            f"子目录「{DATA_SUBDIR}」已存在且非空，请更换位置或先清空该文件夹",
        )
    return sub, f"所选目录非空，将自动使用子文件夹 {DATA_SUBDIR}"


@router.get("/system/pick-folder")
def pick_folder_api():
    """弹出系统文件夹选择框（Windows）。"""
    if sys.platform != "win32":
        raise HTTPException(501, "文件夹选择仅支持 Windows")
    try:
        path, err = folder_dialog.pick_folder("选择数据存储位置")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"无法打开文件夹选择框：{exc}") from exc
    if err:
        raise HTTPException(500, f"无法打开文件夹选择框：{err}")
    if not path:
        return {"path": None, "cancelled": True}
    return {"path": path, "cancelled": False}


@router.post("/system/preview-data-dir")
def preview_data_dir(body: MoveDataIn):
    """预览迁移后的实际目录路径。"""
    target, note = _resolve_migration_target(body.target_dir)
    return {"target_dir": str(target), "note": note}


@router.post("/system/move-data")
def move_data(body: MoveDataIn):
    """把数据目录迁移到新位置，写入 data_location.txt，需重启生效。"""
    target, _note = _resolve_migration_target(body.target_dir)
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise HTTPException(400, "目标目录非空，无法迁移")

    # 关闭数据库连接，确保 SQLite 文件落盘可移动
    engine.dispose()

    try:
        # 移动 data 目录下的所有内容
        for item in DATA_DIR.iterdir():
            shutil.move(str(item), str(target / item.name))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"迁移失败：{e}") from e

    # 写入新位置记录
    (ROOT_DIR / "data_location.txt").write_text(str(target), encoding="utf-8")

    return {"ok": True, "new_dir": str(target), "need_restart": True}


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
    # 两套 AI Key 各自的「已配置」标记，密文不下发
    values["ai_score_api_key_set"] = bool(values.get("ai_score_api_key") or values.get("ai_api_key"))
    values["ai_ocr_api_key_set"] = bool(values.get("ai_ocr_api_key") or values.get("ai_api_key"))
    values["ai_score_api_key"] = ""
    values["ai_ocr_api_key"] = ""
    # 旧 key（兼容）也不下发
    values.pop("ai_api_key", None)
    values["ai_api_key_set"] = values["ai_score_api_key_set"]
    values["data_dir"] = str(DATA_DIR)
    return values


class SettingsIn(BaseModel):
    values: dict


# 密钥类字段：留空表示「不修改已保存值」
_SECRET_KEYS = {"ai_score_api_key", "ai_ocr_api_key", "ai_api_key"}


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db)):
    values = {k: v for k, v in body.values.items() if k in settings_svc.DEFAULTS}
    # 空 key 表示不修改已保存的 key
    for k in list(values):
        if k in _SECRET_KEYS and values[k] == "":
            values.pop(k, None)
    settings_svc.set_many(db, values)
    return {"ok": True}


class TestAIIn(BaseModel):
    kind: str  # "score" | "ocr"
    # 可选：传入表单当前值（未保存也能测试）。为空则回退已保存配置。
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@router.post("/settings/test-ai")
def test_ai(body: TestAIIn, db: Session = Depends(get_db)):
    """测试 AI 配置连通性。优先用传入值，为空则回退已保存值（含旧 key 兼容）。"""
    if body.kind == "ocr":
        base = body.base_url or settings_svc.get(db, "ai_ocr_base_url") or settings_svc.get(db, "ai_base_url")
        key = body.api_key or settings_svc.get(db, "ai_ocr_api_key") or settings_svc.get(db, "ai_api_key")
        model = body.model or settings_svc.get(db, "ai_ocr_vision_model") or settings_svc.get(db, "ai_vision_model")
    else:
        base = body.base_url or settings_svc.get(db, "ai_score_base_url") or settings_svc.get(db, "ai_base_url")
        key = body.api_key or settings_svc.get(db, "ai_score_api_key") or settings_svc.get(db, "ai_api_key")
        model = body.model or settings_svc.get(db, "ai_score_text_model") or settings_svc.get(db, "ai_text_model")
    return ai_svc.test_connection(base, key, model)


# ---------- 行情 ----------

@router.get("/market/search/stocks")
def search_stocks(q: str = "", limit: int = 12):
    return market_svc.search_stocks(q, limit=min(limit, 20))


@router.get("/market/lookup/stock")
def lookup_stock(q: str = ""):
    """按代码或名称精确解析单只股票，供前端自动补全。"""
    query = q.strip()
    if not query:
        raise HTTPException(400, "请提供代码或名称")
    digits = "".join(ch for ch in query if ch.isdigit())
    if len(digits) == 6:
        hit = market_svc.lookup_by_code(digits)
        if hit:
            return hit
    code, name = market_svc.resolve_stock(query, query if not digits else "")
    if code and len("".join(ch for ch in code if ch.isdigit())) == 6:
        hit = market_svc.lookup_by_code(code)
        if hit:
            return hit
        return {"code": code, "name": name}
    raise HTTPException(404, "未找到匹配股票")


@router.get("/market/{code}")
def market_daily(code: str, limit: int = 120, db: Session = Depends(get_db)):
    return market_svc.get_daily(db, code, limit)


# ---------- 统计总览 ----------

@router.get("/stats/overview")
def overview(db: Session = Depends(get_db)):
    rate, count = netvalue.node_config(db)
    points = netvalue.build_series(db)
    rounds = rounds_svc.build_rounds(db)
    events = netvalue.compute_node_events(points, rate, count)
    start_day = points[0].day if points else None
    return {
        "state": netvalue.current_state(points, rate, count),
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
        headers={"Content-Disposition": f"attachment; filename=tradingms-backup-{date.today().isoformat()}.json"},
    )


@router.get("/export/markdown")
def export_markdown(db: Session = Depends(get_db)):
    lines = [f"# Trading MS 复盘导出（{date.today().isoformat()}）", ""]
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
        headers={"Content-Disposition": f"attachment; filename=tradingms-reviews-{date.today().isoformat()}.md"},
    )
