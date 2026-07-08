"""单位净值引擎。

账户视作一只基金：初始净值 1.0。
- 入金：按"入金当日之前最近一次已知净值"折算申购份额；
- 出金：同理赎回份额；
- 每日快照：净值 = 当日总资产 / 当前份额。

入出金视为发生在当日快照之前（盘前）。
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from ..models import CapitalFlow, Snapshot

WAVE_RATE = 1.3
NODE_COUNT = 50


@dataclass
class NavPoint:
    day: date
    nav: float
    assets: float
    shares: float


def node_threshold(level: int) -> float:
    return WAVE_RATE ** level


def build_series(db: Session) -> list[NavPoint]:
    flows = db.query(CapitalFlow).order_by(CapitalFlow.flow_date, CapitalFlow.id).all()
    snaps = db.query(Snapshot).order_by(Snapshot.snap_date).all()

    flows_by_day: dict[date, list[CapitalFlow]] = {}
    for f in flows:
        flows_by_day.setdefault(f.flow_date, []).append(f)
    snap_by_day = {s.snap_date: s for s in snaps}

    all_days = sorted(set(flows_by_day) | set(snap_by_day))

    shares = 0.0
    nav = 1.0
    points: list[NavPoint] = []

    for day in all_days:
        for f in flows_by_day.get(day, []):
            signed = f.amount if f.kind in ("initial", "deposit") else -f.amount
            shares += signed / nav
        snap = snap_by_day.get(day)
        if snap is not None and shares > 0:
            nav = snap.total_assets / shares
            assets = snap.total_assets
        else:
            assets = shares * nav
        points.append(NavPoint(day=day, nav=nav, assets=assets, shares=shares))

    return points


def current_state(points: list[NavPoint]) -> dict:
    if not points:
        return {
            "nav": 1.0, "assets": 0.0, "shares": 0.0, "day": None,
            "lit_levels": [], "lit_count": 0, "next_level": 1,
            "next_threshold": node_threshold(1), "next_gap_pct": None,
            "max_nav": 1.0, "drawdown_pct": 0.0,
        }
    last = points[-1]
    lit = [n for n in range(1, NODE_COUNT + 1) if last.nav >= node_threshold(n)]
    next_level = (lit[-1] + 1) if lit else 1
    max_nav = max(p.nav for p in points)
    drawdown = (last.nav / max_nav - 1) * 100 if max_nav > 0 else 0.0
    state = {
        "nav": last.nav,
        "assets": last.assets,
        "shares": last.shares,
        "day": last.day.isoformat(),
        "lit_levels": lit,
        "lit_count": len(lit),
        "max_nav": max_nav,
        "drawdown_pct": drawdown,
    }
    if next_level <= NODE_COUNT:
        threshold = node_threshold(next_level)
        state["next_level"] = next_level
        state["next_threshold"] = threshold
        state["next_gap_pct"] = (threshold / last.nav - 1) * 100
        state["next_assets_target"] = threshold * last.shares
    else:
        state["next_level"] = None
        state["next_threshold"] = None
        state["next_gap_pct"] = None
        state["next_assets_target"] = None
    return state


def compute_node_events(points: list[NavPoint]) -> list[dict]:
    """遍历净值序列，产出节点点亮/熄灭事件史。"""
    events: list[dict] = []
    lit: set[int] = set()
    prev_nav = 1.0
    for p in points:
        for level in range(1, NODE_COUNT + 1):
            threshold = node_threshold(level)
            if prev_nav < threshold <= p.nav and level not in lit:
                lit.add(level)
                events.append({"level": level, "kind": "lit", "date": p.day, "nav": p.nav})
            elif p.nav < threshold <= prev_nav and level in lit:
                lit.discard(level)
                events.append({"level": level, "kind": "extinguished", "date": p.day, "nav": p.nav})
        prev_nav = p.nav
    return events


def node_timing(events: list[dict], start_day: date | None) -> list[dict]:
    """首次达成耗时序列：第 n-1 → n 节点首次点亮间隔天数。"""
    first_lit: dict[int, date] = {}
    for e in events:
        if e["kind"] == "lit" and e["level"] not in first_lit:
            first_lit[e["level"]] = e["date"]
    result = []
    prev_day = start_day
    for level in sorted(first_lit):
        day = first_lit[level]
        days = (day - prev_day).days if prev_day else None
        result.append({"level": level, "first_lit": day.isoformat(), "days_taken": days})
        prev_day = day
    return result
