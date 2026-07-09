"""AI 能力：OpenAI 兼容接口。未配置时优雅降级（抛 AIUnavailable，由路由转为 400）。"""

import base64
import json
import re
from datetime import date

import httpx
from sqlalchemy.orm import Session

from ..models import Snapshot, Trade
from . import market as market_svc
from . import settings as settings_svc

SCORE_DIMENSIONS = {
    "position": "仓位控制",
    "drawdown": "回撤控制",
    "discipline": "计划执行力",
    "entry": "买点质量",
    "exit": "卖点质量",
    "emotion": "情绪管理",
}


class AIUnavailable(Exception):
    pass


def _ai_config(db: Session, vision: bool = False) -> tuple[str, str, str]:
    """返回 (base_url, api_key, model)。vision=True 取截图识别三件套，否则取打分三件套。

    新 key 优先；为空则回退到旧 key（兼容存量配置）。
    """
    if vision:
        base = settings_svc.get(db, "ai_ocr_base_url") or settings_svc.get(db, "ai_base_url")
        key = settings_svc.get(db, "ai_ocr_api_key") or settings_svc.get(db, "ai_api_key")
        model = settings_svc.get(db, "ai_ocr_vision_model") or settings_svc.get(db, "ai_vision_model")
    else:
        base = settings_svc.get(db, "ai_score_base_url") or settings_svc.get(db, "ai_base_url")
        key = settings_svc.get(db, "ai_score_api_key") or settings_svc.get(db, "ai_api_key")
        model = settings_svc.get(db, "ai_score_text_model") or settings_svc.get(db, "ai_text_model")
    return base, key, model


def is_configured(db: Session, vision: bool = False) -> bool:
    base, key, model = _ai_config(db, vision=vision)
    return bool(base and key and model)


def _chat(db: Session, messages: list[dict], vision: bool = False) -> str:
    base, key, model = _ai_config(db, vision=vision)
    if not (base and key and model):
        raise AIUnavailable(
            "AI 未配置：请在设置中填写" + ("截图识别" if vision else "操作打分") + "的 Base URL、API Key 和模型名"
        )
    resp = httpx.post(
        f"{base.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": messages, "temperature": 0.2},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _extract_json(text: str):
    """模型偶尔会包 markdown 代码块，做一层剥离。"""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError(f"AI 返回内容中未找到 JSON: {text[:200]}")
    return json.loads(text[start:])


def score_review(db: Session, review_date: date, review_texts: dict[str, str]) -> dict:
    trades = db.query(Trade).filter(Trade.trade_date == review_date).all()
    trade_lines = [
        f"- {t.side == 'buy' and '买入' or '卖出'} {t.name or t.code}({t.code}) "
        f"{t.qty}股 @ {t.price}元"
        for t in trades
    ] or ["（当日无交易）"]

    snap = db.query(Snapshot).filter(Snapshot.snap_date == review_date).first()
    prev_snap = (
        db.query(Snapshot)
        .filter(Snapshot.snap_date < review_date)
        .order_by(Snapshot.snap_date.desc())
        .first()
    )
    asset_line = "（无资产快照）"
    if snap:
        asset_line = f"当日收盘总资产 {snap.total_assets:.2f} 元"
        if prev_snap and prev_snap.total_assets:
            change = (snap.total_assets / prev_snap.total_assets - 1) * 100
            asset_line += f"，较前一交易日 {change:+.2f}%"

    codes = sorted({t.code for t in trades})
    market_text = market_svc.market_context_text(db, codes, review_date)

    dims_desc = "、".join(f"{k}({v})" for k, v in SCORE_DIMENSIONS.items())
    prompt = f"""你是一位严格的 A 股交易教练。请根据以下信息，对交易者当日操作按 6 个维度打分（0-10 整数）并给出一句话点评，最后给出总评。

## 日期
{review_date.isoformat()}

## 当日行情
{market_text}

## 当日交易
{chr(10).join(trade_lines)}

## 账户
{asset_line}

## 交易者自述
盘面观察：{review_texts.get('market_observation') or '（未填写）'}
决策复盘：{review_texts.get('decision_review') or '（未填写）'}
错误教训：{review_texts.get('mistakes') or '（未填写）'}
次日计划（前一日写的今日计划可对照执行力）：{review_texts.get('plan') or '（无）'}

## 输出要求
严格输出 JSON，不要多余文字：
{{"scores": {{{", ".join(f'"{k}": {{"score": 0, "comment": ""}}' for k in SCORE_DIMENSIONS)}}}, "summary": "总评"}}
维度含义：{dims_desc}。当日无交易时，重点评估仓位/回撤/情绪与复盘质量，交易类维度可给中性分并注明。"""

    content = _chat(db, [{"role": "user", "content": prompt}])
    return _extract_json(content)


SCREENSHOT_PROMPT = """这是一张同花顺（或类似券商软件）的成交记录/持仓截图。请提取其中的交易记录，严格输出 JSON 数组，不要多余文字：
[{"date": "YYYY-MM-DD", "code": "6位股票代码", "name": "股票名称", "side": "buy或sell", "price": 成交价, "qty": 成交数量}]
注意：
- side 依据"买入/卖出/证券买入/证券卖出"等字样判断
- 如果截图是持仓页（没有买卖方向），输出每行持仓为 {"date": null, "code": ..., "name": ..., "side": "hold", "price": 成本价, "qty": 持仓数量}
- 识别不到任何记录则输出 []"""


def parse_screenshot(db: Session, image_bytes: bytes, mime: str) -> list[dict]:
    b64 = base64.b64encode(image_bytes).decode()
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": SCREENSHOT_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ],
    }]
    content = _chat(db, messages, vision=True)
    data = _extract_json(content)
    return data if isinstance(data, list) else []
