"""根据 dist/data 中 2026-07-10 数据生成打印预览 HTML。"""
from __future__ import annotations

import html
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "dist" / "data" / "laimiutrade.db"
DAY = "2026-07-10"
OUT = ROOT / "preview" / f"daily-review-{DAY}.html"
CSS_FILE = ROOT / "frontend" / "src" / "styles.css"

SCORE_DIMS = {
    "entry": "买点",
    "exit": "卖点",
    "position": "仓位",
    "discipline": "纪律",
    "emotion": "情绪",
    "plan": "计划",
}


def esc(s: str | None) -> str:
    return html.escape(s or "")


def load_json(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def score_for_dots(entry: dict) -> int:
    ai = entry.get("ai")
    final = entry.get("final")
    if ai is not None and final is not None and final != ai:
        return int(final)
    if ai is not None:
        return int(ai)
    if final is not None:
        return int(final)
    return 0


def trade_summary(ts: dict) -> str:
    raw = ts.get("_summary")
    if isinstance(raw, dict):
        return str(raw.get("comment") or "")
    return ""


def trade_avg(ts: dict) -> int | None:
    vals = []
    for dim in SCORE_DIMS:
        entry = ts.get(dim)
        if isinstance(entry, dict):
            v = entry.get("ai") if entry.get("ai") is not None else entry.get("final")
            if v is not None:
                vals.append(int(v))
    if not vals:
        return None
    return round(sum(vals) / len(vals))


def trade_has_analysis(ts: dict) -> bool:
    if trade_summary(ts):
        return True
    return any(
        isinstance(ts.get(dim), dict)
        and (ts[dim].get("ai") is not None or ts[dim].get("final") is not None or ts[dim].get("comment"))
        for dim in SCORE_DIMS
    )


def fmt_cn_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(m)}月{int(d)}日"


def fmt_money(v: float | int | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}"


def render_inline_md(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(text))


def render_markdown(text: str) -> str:
    blocks: list[str] = []
    list_buf: list[str] = []

    def flush_list() -> None:
        if not list_buf:
            return
        items = "".join(f"<li>{render_inline_md(item)}</li>" for item in list_buf)
        blocks.append(f'<ul class="print-md-list">{items}</ul>')
        list_buf.clear()

    for raw in text.replace("\r\n", "\n").split("\n"):
        t = raw.strip()
        if not t:
            flush_list()
            continue
        m = re.match(r"^#{1,6}\s+(.+)$", t)
        if m:
            flush_list()
            blocks.append(f'<div class="print-md-heading">{render_inline_md(m.group(1))}</div>')
            continue
        m = re.match(r"^[-*•]\s+(.+)$", t)
        if m:
            list_buf.append(m.group(1))
            continue
        m = re.match(r"^\d+\.\s+(.+)$", t)
        if m:
            list_buf.append(m.group(1))
            continue
        flush_list()
        blocks.append(f'<p class="print-md-p">{render_inline_md(t)}</p>')
    flush_list()
    return '<div class="print-markdown">' + "".join(blocks) + "</div>"


def render_score_rows(scores: dict, side: str | None = None) -> str:
    rows = []
    for dim, label in SCORE_DIMS.items():
        dim_label = label
        if dim == "entry" and side == "sell":
            dim_label = "买点质量"
        elif dim == "exit" and side == "buy":
            dim_label = "卖点质量"
        inactive = (dim == "entry" and side == "sell") or (dim == "exit" and side == "buy")
        entry = scores.get(dim) or {}
        if inactive and entry.get("ai") is None and entry.get("final") is None and not entry.get("comment"):
            continue
        score = score_for_dots(entry)
        has = score > 0
        width = f"{score * 10}%" if has else "0%"
        num = f"{score}/10" if has else "—"
        comment = ""
        if entry.get("comment"):
            comment = f'<div class="print-score-comment">{esc(entry["comment"])}</div>'
        rows.append(
            f'<div class="print-score-row">'
            f'<span class="print-score-dim">{esc(dim_label)}</span>'
            f'<div class="print-score-bar-wrap">'
            f'<div class="print-score-bar"><div class="print-score-fill" style="width:{width}"></div></div>'
            f'<span class="print-score-num">{num}</span></div>{comment}</div>'
        )
    if not rows:
        return '<p class="print-muted">暂无评分</p>'
    return '<div class="print-score-grid">' + "".join(rows) + "</div>"


def render_text_block(label: str, text: str) -> str:
    empty = not (text or "").strip()
    body = esc(text.strip()) if not empty else "（未填写）"
    cls = " is-empty" if empty else ""
    return (
        f'<div class="print-text-block{cls}">'
        f'<div class="print-text-label">{esc(label)}</div>'
        f'<div class="print-text-body">{body}</div></div>'
    )


def render_summary(label: str, text: str) -> str:
    if not (text or "").strip():
        return ""
    return (
        f'<div class="print-summary-box">'
        f'<div class="print-summary-label">{esc(label)}</div>'
        f'<div class="print-summary-body">{esc(text)}</div></div>'
    )


def render_section(title: str, body: str) -> str:
    return (
        f'<section class="print-section-card">'
        f'<h2 class="print-section-title">{esc(title)}</h2>'
        f'<div class="print-section-body">{body}</div></section>'
    )


def extract_print_css() -> str:
    text = CSS_FILE.read_text(encoding="utf-8")
    start = text.index("@media print {")
    depth = 0
    end = start
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    block = text[start:end]
    # 预览页始终应用打印样式
    inner = block.replace("@media print {", "").rsplit("}", 1)[0]
    base = """
:root {
  --bg: #f5f0e6; --surface: #ffffff; --surface-2: #fbf7ef; --surface-3: #f1e9da;
  --border: #e6dcc6; --border-strong: #d2c4a3;
  --text: #3a322a; --text-2: #7a6f5e; --text-3: #a89c86;
  --gold: #e8a87c; --gold-bright: #d98a52; --gold-dim: rgba(232, 168, 124, 0.22);
  --up: #ff6b6b; --down: #4ecdc4;
  --font-body: "PingFang SC", "Microsoft YaHei", "Segoe UI", system-ui, sans-serif;
  --font-display: Georgia, "Times New Roman", "STZhongsong", "SimSun", serif;
  --font-mono: Consolas, "Cascadia Code", monospace;
  --radius-sm: 6px; --radius-md: 10px;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 24px;
  background: var(--bg); color: var(--text);
  font-family: var(--font-body); font-size: 11.5px; line-height: 1.55;
}
.preview-banner {
  max-width: 900px; margin: 0 auto 16px; padding: 10px 14px;
  background: #fff8e8; border: 1px dashed var(--gold-bright); border-radius: 8px;
  font-size: 12px; color: var(--text-2);
}
.print-document { max-width: 900px; margin: 0 auto; }
"""
    return base + inner


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"数据库不存在: {DB}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    username = ""
    row = c.execute("SELECT value FROM settings WHERE key='pdf_username'").fetchone()
    if row and row["value"]:
        username = row["value"]

    review = c.execute("SELECT * FROM daily_reviews WHERE review_date=?", (DAY,)).fetchone()
    if not review:
        raise SystemExit(f"未找到 {DAY} 日复盘")

    data = dict(review)
    trade_scores = load_json(data.get("trade_scores"), {})
    scores = load_json(data.get("scores"), {})
    watchlist = load_json(data.get("next_watchlist"), [])
    rehearsal = load_json(data.get("next_position_rehearsal"), [])

    trades = [dict(r) for r in c.execute(
        "SELECT id, code, name, side, price, qty, fee_commission, fee_stamp, fee_transfer "
        "FROM trades WHERE trade_date=? ORDER BY id", (DAY,)
    )]
    for t in trades:
        t["fees"] = round(
            (t.get("fee_commission") or 0)
            + (t.get("fee_stamp") or 0)
            + (t.get("fee_transfer") or 0),
            2,
        )

    snap = c.execute("SELECT * FROM snapshots WHERE snap_date=?", (DAY,)).fetchone()
    snapshot = None
    if snap:
        snapshot = dict(snap)
        snapshot["positions"] = load_json(snapshot.get("positions"), [])

    author = username or "交易者"
    printed_at = datetime.now().strftime("%Y/%m/%d %H:%M")
    trade_count = len(trades)

    parts: list[str] = []

    # header
    badge = f'<span class="print-doc-badge">{trade_count} 笔交易</span>' if trade_count else ""
    parts.append(
        f'<header class="print-doc-header">'
        f'<div class="print-doc-brand-row">'
        f'<span class="print-doc-mark">Trading MS</span>'
        f'<span class="print-doc-printed">预览生成于 {printed_at}</span></div>'
        f'<h1 class="print-doc-title">每日复盘</h1>'
        f'<div class="print-doc-meta-row">'
        f'<span class="print-doc-meta">{esc(author)} · {fmt_cn_date(DAY)} · {DAY}</span>{badge}</div>'
        f"</header>"
    )

    if snapshot:
        hero = (
            f'<div class="print-daily-hero">'
            f'<div class="print-daily-hero-item"><span class="print-daily-hero-label">总资产</span>'
            f'<span class="print-daily-hero-value">¥{fmt_money(snapshot.get("total_assets"))}</span></div>'
        )
        pos_n = len(snapshot.get("positions") or [])
        if pos_n:
            hero += (
                f'<div class="print-daily-hero-item"><span class="print-daily-hero-label">持仓数</span>'
                f'<span class="print-daily-hero-value">{pos_n}</span></div>'
            )
        hero += "</div>"
        table = ""
        if pos_n:
            rows = "".join(
                f"<tr><td class='mono'>{esc(p.get('code'))}</td><td>{esc(p.get('name'))}</td>"
                f"<td class='num mono'>{p.get('qty', '')}</td></tr>"
                for p in snapshot["positions"]
            )
            table = (
                '<table class="print-table print-table-elegant">'
                "<thead><tr><th>代码</th><th>名称</th><th class='num'>数量</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>"
            )
        parts.append(render_section("收盘概览", hero + table))

    # trades
    trade_html = []
    if not trades:
        trade_html.append('<p class="print-muted">当日无交易</p>')
    else:
        for t in trades:
            ts = trade_scores.get(str(t["id"]), {})
            summary = trade_summary(ts)
            avg = trade_avg(ts)
            side_cls = "buy" if t["side"] == "buy" else "sell"
            side_txt = "买" if t["side"] == "buy" else "卖"
            tags = ""
            if avg is not None:
                tags += f'<span class="print-tag gold">均分 {avg}</span>'
            trade_html.append(
                f'<div class="print-trade-card">'
                f'<div class="print-trade-card-head">'
                f'<span class="print-trade-side {side_cls}">{side_txt}</span>'
                f'<div class="print-trade-card-info">'
                f'<div class="print-trade-card-name">{esc(t.get("name") or t.get("code"))}</div>'
                f'<div class="print-trade-card-meta mono">{esc(t.get("code"))} · {t.get("price")} × {t.get("qty")}</div>'
                f"</div><div class='print-trade-card-tags'>{tags}</div></div>"
                f"{render_summary('AI 总评', summary)}"
                + (render_score_rows(ts, t.get("side")) if trade_has_analysis(ts) else '<p class="print-muted">未分析</p>')
                + "</div>"
            )
    parts.append(render_section("当日交易与 AI 分析", "".join(trade_html)))

    daily_body = render_score_rows(scores) + render_summary("整日 AI 总评", data.get("ai_summary") or "")
    parts.append(render_section("整日操作概览", daily_body))

    text_body = (
        render_text_block("盘面观察 · 大盘 / 板块 / 市场情绪", data.get("market_observation") or "")
        + render_text_block("决策复盘 · 每笔操作的理由与对错", data.get("decision_review") or "")
        + render_text_block("错误与教训", data.get("mistakes") or "")
    )
    parts.append(render_section("复盘正文", text_body))

    if rehearsal:
        rows = "".join(
            f"<tr><td class='mono'>{esc(p.get('code'))}</td><td>{esc(p.get('name'))}</td>"
            f"<td class='num mono'>{p.get('qty', 0)} 股</td><td>{esc(p.get('note') or '—')}</td></tr>"
            for p in rehearsal
        )
        parts.append(render_section(
            "明日操作预演",
            '<table class="print-table print-table-elegant"><thead><tr>'
            "<th>代码</th><th>名称</th><th class='num'>预演持仓</th><th>备注</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>",
        ))

    if (data.get("rehearsal_ai_analysis") or "").strip():
        parts.append(render_section(
            "明日预演 AI 分析",
            render_markdown(data["rehearsal_ai_analysis"]),
        ))

    next_body = (
        render_text_block("大盘预判", data.get("next_market_forecast") or "")
        + render_text_block("仓位计划", data.get("next_position_plan") or "")
        + render_text_block("风险预案", data.get("next_risk_plan") or "")
    )
    if watchlist:
        rows = "".join(
            f"<tr><td class='mono'>{esc(w.get('code') or '—')}</td><td>{esc(w.get('name') or '—')}</td>"
            f"<td>{esc(w.get('condition') or '—')}</td><td>{esc(w.get('action') or '—')}</td></tr>"
            for w in watchlist
        )
        next_body += (
            '<table class="print-table print-table-elegant" style="margin-top:12px"><thead><tr>'
            "<th>代码</th><th>名称</th><th>触发条件</th><th>计划动作</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    parts.append(render_section("次日预研", next_body))

    parts.append(
        '<footer class="print-doc-footer">'
        "<span>Trading MS · 交易者管理系统</span>"
        "<span>仅供个人复盘存档</span></footer>"
    )

    doc = '<article class="print-document">' + "".join(parts) + "</article>"
    css = extract_print_css()
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(author)} Trading MS {fmt_cn_date(DAY)} 复盘预览</title>
<style>{css}</style>
</head>
<body>
<div class="preview-banner">📄 这是根据你 <strong>{DAY}</strong> 真实数据生成的打印预览（数据源：dist/data）。在浏览器中按 Ctrl+P 可另存为 PDF。</div>
{doc}
</body>
</html>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"已生成: {OUT}")
    print(f"交易笔数: {trade_count}")
    conn.close()


if __name__ == "__main__":
    main()
