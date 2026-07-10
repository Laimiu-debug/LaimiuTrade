"""根据 dist/data 真实数据生成周复盘打印预览 HTML。"""
from __future__ import annotations

import html
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from generate_print_preview import CSS_FILE, esc, extract_print_css, render_section  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "dist" / "data" / "laimiutrade.db"
YEAR = 2026
WEEK = 28
OUT = ROOT / "preview" / f"weekly-review-{YEAR}-W{WEEK}.html"


def week_range(year: int, week: int) -> tuple[date, date]:
    start = date.fromisocalendar(year, week, 1)
    return start, start + timedelta(days=6)


def fmt_money(v: float | int | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}"


def fmt_pct(v: float | int | None, signed: bool = True) -> str:
    if v is None:
        return "—"
    prefix = "+" if signed and v > 0 else ""
    return f"{prefix}{v:.2f}%"


def build_rounds(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, trade_date, code, name, side, price, qty, "
        "fee_commission, fee_stamp, fee_transfer "
        "FROM trades ORDER BY trade_date, id"
    ).fetchall()
    by_code: dict[str, list] = {}
    for r in rows:
        by_code.setdefault(r["code"], []).append(r)

    rounds: list[dict] = []
    for code, items in by_code.items():
        position = 0
        current: list = []
        for t in items:
            if position == 0 and t["side"] == "sell":
                rounds.append(_make_round(code, [t], 0, anomaly=True))
                continue
            current.append(t)
            position += t["qty"] if t["side"] == "buy" else -t["qty"]
            if position <= 0:
                rounds.append(_make_round(code, current, position))
                current = []
                position = 0
        if current:
            rounds.append(_make_round(code, current, position))
    rounds.sort(key=lambda r: r["start_date"], reverse=True)
    return rounds


def _make_round(code: str, trades: list, position_after: int, anomaly: bool = False) -> dict:
    buy_amount = sum(t["price"] * t["qty"] for t in trades if t["side"] == "buy")
    sell_amount = sum(t["price"] * t["qty"] for t in trades if t["side"] == "sell")
    fees = sum(
        (t["fee_commission"] or 0) + (t["fee_stamp"] or 0) + (t["fee_transfer"] or 0)
        for t in trades
    )
    closed = position_after == 0 and not anomaly
    pnl = sell_amount - buy_amount - fees if closed else None
    pnl_pct = (pnl / buy_amount * 100) if closed and buy_amount > 0 else None
    name = next((t["name"] for t in reversed(trades) if t["name"]), "")
    return {
        "code": code,
        "name": name,
        "start_date": trades[0]["trade_date"],
        "end_date": trades[-1]["trade_date"] if closed else None,
        "status": "closed" if closed else ("anomaly" if anomaly else "open"),
        "pnl": round(pnl, 2) if pnl is not None else None,
        "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
    }


def build_nav_series(conn: sqlite3.Connection) -> list[tuple[date, float]]:
    flows = conn.execute(
        "SELECT flow_date, kind, amount FROM capital_flows ORDER BY flow_date, id"
    ).fetchall()
    snaps = conn.execute(
        "SELECT snap_date, total_assets FROM snapshots ORDER BY snap_date"
    ).fetchall()
    flows_by_day: dict[str, list] = {}
    for f in flows:
        flows_by_day.setdefault(f["flow_date"], []).append(f)
    snap_by_day = {s["snap_date"]: s["total_assets"] for s in snaps}
    all_days = sorted(set(flows_by_day) | set(snap_by_day))
    shares = 0.0
    nav = 1.0
    points: list[tuple[date, float]] = []
    for day_s in all_days:
        for f in flows_by_day.get(day_s, []):
            signed = f["amount"] if f["kind"] in ("initial", "deposit") else -f["amount"]
            shares += signed / nav
        if day_s in snap_by_day and shares > 0:
            nav = snap_by_day[day_s] / shares
        points.append((date.fromisoformat(day_s), nav))
    return points


def period_auto(conn: sqlite3.Connection, start: date, end: date) -> dict:
    points = build_nav_series(conn)
    in_range = [p for p in points if start <= p[0] <= end]
    before = [p for p in points if p[0] < start]
    start_nav = before[-1][1] if before else (in_range[0][1] if in_range else 1.0)
    end_nav = in_range[-1][1] if in_range else start_nav
    ret = (end_nav / start_nav - 1) * 100 if start_nav > 0 else 0.0
    peak = start_nav
    mdd = 0.0
    for _, nav in in_range:
        peak = max(peak, nav)
        if peak > 0:
            mdd = min(mdd, (nav / peak - 1) * 100)
    rounds = build_rounds(conn)
    closed_in = [
        r for r in rounds
        if r["status"] == "closed" and r["end_date"] and start.isoformat() <= r["end_date"] <= end.isoformat()
    ]
    trade_count = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE trade_date >= ? AND trade_date <= ?",
        (start.isoformat(), end.isoformat()),
    ).fetchone()[0]
    return {
        "return_pct": round(ret, 2),
        "max_drawdown_pct": round(mdd, 2),
        "end_nav": round(end_nav, 4),
        "trade_count": trade_count,
        "closed_rounds": len(closed_in),
        "round_pnl": round(sum(r["pnl"] or 0 for r in closed_in), 2),
        "win_rounds": len([r for r in closed_in if (r["pnl"] or 0) > 0]),
    }


def round_summaries(conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
    rows = conn.execute("SELECT code, start_date, review_summary FROM round_reviews").fetchall()
    return {(r["code"], r["start_date"]): (r["review_summary"] or "").strip() for r in rows}


def render_stat_card(label: str, value: str, tone: str | None = None, note: str = "") -> str:
    tone_cls = f" {tone}" if tone else ""
    note_html = f'<div class="print-stat-note">{esc(note)}</div>' if note else ""
    return (
        f'<div class="print-stat-card">'
        f'<div class="print-stat-label">{esc(label)}</div>'
        f'<div class="print-stat-value{tone_cls}">{esc(value)}</div>{note_html}</div>'
    )


def render_stat_grid(auto: dict) -> str:
    win_note = f"盈 {auto['win_rounds']} / {auto['closed_rounds']}" if auto["closed_rounds"] > 0 else ""
    ret_tone = "pos" if auto["return_pct"] >= 0 else "neg"
    pnl_tone = "pos" if auto["round_pnl"] >= 0 else "neg"
    cards = [
        render_stat_card("区间收益", fmt_pct(auto["return_pct"]), ret_tone),
        render_stat_card("区间最大回撤", fmt_pct(auto["max_drawdown_pct"], signed=False)),
        render_stat_card("期末净值", f"{auto['end_nav']:.4f}"),
        render_stat_card(
            "交易 / 清仓回合",
            f"{auto['trade_count']} / {auto['closed_rounds']}",
            note=win_note,
        ),
        render_stat_card("回合盈亏", f"¥{fmt_money(auto['round_pnl'])}", pnl_tone),
    ]
    return '<div class="print-stat-grid">' + "".join(cards) + "</div>"


def render_text_block_plain(label: str, text: str) -> str:
    empty = not (text or "").strip()
    body = esc(text.strip()) if not empty else "（未填写）"
    cls = "print-text-block is-empty print-text-block--plain" if empty else "print-text-block print-text-block--plain"
    return (
        f'<div class="{cls}">'
        f'<div class="print-text-label">{esc(label)}</div>'
        f'<div class="print-text-body">{body}</div></div>'
    )


def render_period_rounds(rounds: list[dict], summaries: dict[tuple[str, str], str]) -> str:
    closed = [r for r in rounds if r["status"] == "closed"]
    wins = [r for r in closed if (r["pnl"] or 0) > 0]
    losses = [r for r in closed if (r["pnl"] or 0) <= 0]
    total_pnl = sum(r["pnl"] or 0 for r in closed)
    summary = (
        f"{wins.__len__()} 盈 · {losses.__len__()} 亏 · 合计 ¥{fmt_money(total_pnl)}"
        if closed
        else f"{len(rounds)} 笔"
    )
    cards = []
    for r in rounds:
        text = summaries.get((r["code"], r["start_date"]), "")
        pnl = r.get("pnl")
        win = pnl is not None and pnl >= 0
        lose = pnl is not None and pnl < 0
        if pnl is not None:
            badge = (
                f'<div class="print-round-pnl-badge{" win" if win else " lose" if lose else ""}">'
                f'<span class="print-round-pnl-amt mono">¥{fmt_money(pnl)}</span>'
                f'<span class="print-round-pnl-pct mono">{fmt_pct(r.get("pnl_pct"))}</span></div>'
            )
        else:
            badge = '<span class="print-round-status-tag">持仓中</span>'
        snippet = (
            f'<p class="print-round-snippet">{esc(text)}</p>'
            if text
            else '<p class="print-round-snippet is-empty">（未填写回合复盘摘要）</p>'
        )
        cards.append(
            f'<div class="print-round-card">'
            f'<div class="print-round-card-top">'
            f'<div class="print-round-card-main">'
            f'<div class="print-round-card-name">{esc(r["name"])}</div>'
            f'<div class="print-round-card-meta mono">{esc(r["code"])} · {esc(r["start_date"])} → '
            f'{esc(r["end_date"] or "持仓中")}</div></div>{badge}</div>{snippet}</div>'
        )
    return (
        f'<div class="print-rounds-block">'
        f'<div class="print-rounds-summary">{esc(summary)}</div>'
        f'<div class="print-rounds-list">{"".join(cards)}</div></div>'
    )


def write_preview_page(title: str, banner: str, doc_html: str, out: Path) -> None:
    css = extract_print_css()
    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{css}</style>
</head>
<body>
<div class="preview-banner">{banner}</div>
{doc_html}
</body>
</html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"数据库不存在: {DB}")
    if not CSS_FILE.exists():
        raise SystemExit(f"样式文件不存在: {CSS_FILE}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    username = ""
    row = conn.execute("SELECT value FROM settings WHERE key='pdf_username'").fetchone()
    if row and row["value"]:
        username = row["value"]

    review = conn.execute(
        "SELECT * FROM weekly_reviews WHERE year=? AND week=?",
        (YEAR, WEEK),
    ).fetchone()
    if not review:
        raise SystemExit(f"未找到 {YEAR} 年第 {WEEK} 周复盘")

    start, end = week_range(YEAR, WEEK)
    auto = period_auto(conn, start, end)
    all_rounds = build_rounds(conn)
    period_rounds = [
        r for r in all_rounds
        if r["status"] == "closed" and r["end_date"] and start.isoformat() <= r["end_date"] <= end.isoformat()
    ]
    period_rounds.sort(key=lambda r: r.get("end_date") or "", reverse=True)
    summaries = round_summaries(conn)

    author = username or "交易者"
    printed_at = datetime.now().strftime("%Y/%m/%d %H:%M")
    period_label = f"{start.isoformat()} ~ {end.isoformat()}"

    parts = [
        (
            f'<header class="print-doc-header">'
            f'<div class="print-doc-brand-row">'
            f'<span class="print-doc-mark">Trading MS</span>'
            f'<span class="print-doc-printed">预览生成于 {printed_at}</span></div>'
            f'<h1 class="print-doc-title">周复盘</h1>'
            f'<div class="print-doc-meta-row">'
            f'<span class="print-doc-meta">{esc(author)} · {YEAR} 第 {WEEK} 周 · {period_label}</span>'
            f"</div></header>"
        ),
        render_section("区间统计", render_stat_grid(auto)),
    ]
    if period_rounds:
        parts.append(render_section("本周清仓回合", render_period_rounds(period_rounds, summaries)))
    parts.append(
        render_section(
            "复盘正文",
            render_text_block_plain("本周盘面回顾", review["market_review"])
            + render_text_block_plain("本周做对的事", review["right_things"])
            + render_text_block_plain("本周做错的事", review["wrong_things"])
            + render_text_block_plain("下周策略", review["next_strategy"]),
        )
    )
    parts.append(
        '<footer class="print-doc-footer">'
        "<span>Trading MS · 交易者管理系统</span>"
        "<span>仅供个人复盘存档</span></footer>"
    )

    doc = '<article class="print-document">' + "".join(parts) + "</article>"
    banner = (
        f"📄 周复盘打印预览（<strong>{YEAR} 第 {WEEK} 周</strong> · {period_label}）"
        f" — 数据源 dist/data，样式与当前前端打印一致。按 Ctrl+P 可另存 PDF。"
    )
    write_preview_page(f"{author} Trading MS {YEAR}W{WEEK} 周复盘预览", banner, doc, OUT)
    print(f"已生成: {OUT}")
    print(f"清仓回合: {len(period_rounds)} · 区间收益: {fmt_pct(auto['return_pct'])}")
    conn.close()


if __name__ == "__main__":
    main()
