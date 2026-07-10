import sqlite3
from pathlib import Path

for p in [
    Path(r"E:/Laimiutrade/data/laimiutrade.db"),
    Path(r"E:/Laimiutrade/dist/data/laimiutrade.db"),
]:
    print("===", p)
    if not p.exists():
        print("missing")
        continue
    print("size", p.stat().st_size)
    c = sqlite3.connect(p)
    for t in ["daily_reviews", "trades", "snapshots", "weekly_reviews", "monthly_reviews", "settings"]:
        try:
            n = c.execute(f"select count(*) from {t}").fetchone()[0]
            print(f"  {t}: {n}")
        except Exception as e:
            print(f"  {t}: {e}")
    print("  daily dates:", [r[0] for r in c.execute(
        "select review_date from daily_reviews order by review_date desc limit 15"
    )])
    print("  july trades:", [r[0] for r in c.execute(
        "select distinct trade_date from trades where trade_date like '2026-07%' order by trade_date"
    )])
    c.close()
