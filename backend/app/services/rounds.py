"""回合归组：同一标的从建仓（持仓 0 → 正）到清仓（回到 0）为一个回合。"""

from sqlalchemy.orm import Session

from ..models import Trade


def _trade_dict(t: Trade) -> dict:
    fees = t.fee_commission + t.fee_stamp + t.fee_transfer
    return {
        "id": t.id,
        "date": t.trade_date.isoformat(),
        "code": t.code,
        "name": t.name,
        "side": t.side,
        "price": t.price,
        "qty": t.qty,
        "fees": round(fees, 2),
        "note": t.note,
        "source": t.source,
    }


def build_rounds(db: Session) -> list[dict]:
    trades = db.query(Trade).order_by(Trade.trade_date, Trade.id).all()
    by_code: dict[str, list[Trade]] = {}
    for t in trades:
        by_code.setdefault(t.code, []).append(t)

    rounds: list[dict] = []
    for code, items in by_code.items():
        position = 0
        current: list[Trade] = []
        for t in items:
            if position == 0 and t.side == "sell":
                # 数据异常（无持仓先卖），单独成组避免污染
                rounds.append(_make_round(code, [t], position_after=0, anomaly=True))
                continue
            current.append(t)
            position += t.qty if t.side == "buy" else -t.qty
            if position <= 0:
                rounds.append(_make_round(code, current, position_after=position))
                current = []
                position = 0
        if current:
            rounds.append(_make_round(code, current, position_after=position))

    rounds.sort(key=lambda r: r["start_date"], reverse=True)
    return rounds


def _make_round(code: str, trades: list[Trade], position_after: int, anomaly: bool = False) -> dict:
    buy_amount = sum(t.price * t.qty for t in trades if t.side == "buy")
    sell_amount = sum(t.price * t.qty for t in trades if t.side == "sell")
    fees = sum(t.fee_commission + t.fee_stamp + t.fee_transfer for t in trades)
    closed = position_after == 0 and not anomaly
    pnl = sell_amount - buy_amount - fees if closed else None
    pnl_pct = (pnl / buy_amount * 100) if closed and buy_amount > 0 else None
    name = next((t.name for t in reversed(trades) if t.name), "")
    return {
        "code": code,
        "name": name,
        "start_date": trades[0].trade_date.isoformat(),
        "end_date": trades[-1].trade_date.isoformat() if closed else None,
        "status": "closed" if closed else ("anomaly" if anomaly else "open"),
        "position": position_after,
        "buy_amount": round(buy_amount, 2),
        "sell_amount": round(sell_amount, 2),
        "fees": round(fees, 2),
        "pnl": round(pnl, 2) if pnl is not None else None,
        "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
        "trades": [_trade_dict(t) for t in trades],
    }


def round_stats(rounds: list[dict]) -> dict:
    closed = [r for r in rounds if r["status"] == "closed"]
    closed.sort(key=lambda r: r["end_date"] or "")
    wins = [r for r in closed if (r["pnl"] or 0) > 0]
    losses = [r for r in closed if (r["pnl"] or 0) <= 0]

    win_streak = lose_streak = cur_win = cur_lose = 0
    for r in closed:
        if (r["pnl"] or 0) > 0:
            cur_win += 1
            cur_lose = 0
        else:
            cur_lose += 1
            cur_win = 0
        win_streak = max(win_streak, cur_win)
        lose_streak = max(lose_streak, cur_lose)

    avg_win = sum(r["pnl"] for r in wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(r["pnl"] for r in losses) / len(losses)) if losses else 0.0
    return {
        "total_rounds": len(closed),
        "open_rounds": len([r for r in rounds if r["status"] == "open"]),
        "win_count": len(wins),
        "lose_count": len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else None,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_loss_ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else None,
        "max_win_streak": win_streak,
        "max_lose_streak": lose_streak,
        "total_pnl": round(sum(r["pnl"] for r in closed), 2) if closed else 0.0,
    }
