"""导出指定日期的复盘打印预览 HTML。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import DB_PATH  # noqa: E402

DAY = "2026-07-10"
OUT = ROOT / "preview" / f"daily-review-{DAY}.html"


def main() -> None:
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    username = ""
    row = c.execute("SELECT value FROM settings WHERE key='pdf_username'").fetchone()
    if row:
        username = row["value"] or ""

    review = c.execute(
        "SELECT * FROM daily_reviews WHERE review_date=?", (DAY,)
    ).fetchone()
    if not review:
        recent = [
            r[0]
            for r in c.execute(
                "SELECT review_date FROM daily_reviews ORDER BY review_date DESC LIMIT 10"
            )
        ]
        print(f"未找到 {DAY} 日复盘。最近日期: {recent}")
        sys.exit(1)

    data = dict(review)
    for key in (
        "trade_scores", "scores", "next_watchlist",
        "next_position_rehearsal", "t_groups",
    ):
        raw = data.get(key) or "[]" if key != "trade_scores" and key != "scores" else data.get(key) or "{}"
        if isinstance(raw, str):
            try:
                data[key] = json.loads(raw)
            except json.JSONDecodeError:
                data[key] = {} if key in ("trade_scores", "scores") else []

    trades = [
        dict(r)
        for r in c.execute(
            "SELECT * FROM trades WHERE trade_date=? ORDER BY id", (DAY,)
        )
    ]

    snap_row = c.execute(
        "SELECT * FROM snapshots WHERE snapshot_date=?", (DAY,)
    ).fetchone()
    snapshot = None
    if snap_row:
        snapshot = dict(snap_row)
        if snapshot.get("positions"):
            try:
                snapshot["positions"] = json.loads(snapshot["positions"])
            except json.JSONDecodeError:
                snapshot["positions"] = []

    payload = {
        "username": username,
        "day": DAY,
        "data": {
            **data,
            "trades": trades,
            "snapshot": snapshot,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"exported json -> {OUT.with_suffix('.json')}")
    (OUT.with_suffix(".json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"DB: {DB_PATH}")
    print(f"trades: {len(trades)}")
    conn.close()


if __name__ == "__main__":
    main()
