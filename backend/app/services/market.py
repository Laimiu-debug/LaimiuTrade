"""行情数据三源：本地通达信 vipdoc 直读 / akshare / 东方财富公开接口。

统一输出日K: [{date, open, high, low, close, volume, amount}]
优先级链路由设置 market_priority 控制，逐源尝试直至成功。
"""

import struct
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from . import settings as settings_svc

INDEX_CODES = {"000001.SH", "399001.SZ", "399006.SZ", "000300.SH", "000905.SH"}


def _market_prefix(code: str) -> tuple[str, str]:
    """返回 (市场目录, 纯代码)。支持 '600000'、'000001.SH' 两种写法。"""
    if "." in code:
        pure, suffix = code.split(".")
        return suffix.lower(), pure
    if code.startswith(("6", "5", "9")):
        return "sh", code
    if code.startswith(("4", "8")):
        return "bj", code
    return "sz", code


# ---------- 通达信 ----------

def read_tdx_day(vipdoc: str, code: str, limit: int = 120) -> list[dict]:
    market, pure = _market_prefix(code)
    path = Path(vipdoc) / market / "lday" / f"{market}{pure}.day"
    if not path.exists():
        raise FileNotFoundError(f"通达信数据文件不存在: {path}")
    records: list[dict] = []
    raw = path.read_bytes()
    count = len(raw) // 32
    start = max(0, count - limit)
    for i in range(start, count):
        chunk = raw[i * 32:(i + 1) * 32]
        d, o, h, low, c, amount, vol, _ = struct.unpack("<IIIIIfII", chunk)
        records.append({
            "date": f"{d // 10000:04d}-{d % 10000 // 100:02d}-{d % 100:02d}",
            "open": o / 100, "high": h / 100, "low": low / 100, "close": c / 100,
            "volume": vol, "amount": amount,
        })
    return records


# ---------- akshare ----------

def read_akshare(code: str, limit: int = 120) -> list[dict]:
    import akshare as ak  # noqa: PLC0415 - akshare 导入极慢，仅在启用该源时加载

    market, pure = _market_prefix(code)
    if f"{pure}.{market.upper()}" in INDEX_CODES or (market == "sh" and pure.startswith("000")):
        df = ak.stock_zh_index_daily(symbol=f"{market}{pure}")
        df = df.tail(limit)
        return [
            {
                "date": str(r["date"])[:10], "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "volume": float(r["volume"]), "amount": 0.0,
            }
            for _, r in df.iterrows()
        ]
    df = ak.stock_zh_a_hist(symbol=pure, period="daily", adjust="")
    df = df.tail(limit)
    return [
        {
            "date": str(r["日期"])[:10], "open": float(r["开盘"]), "high": float(r["最高"]),
            "low": float(r["最低"]), "close": float(r["收盘"]),
            "volume": float(r["成交量"]), "amount": float(r["成交额"]),
        }
        for _, r in df.iterrows()
    ]


# ---------- 东方财富 ----------

def read_eastmoney(code: str, limit: int = 120) -> list[dict]:
    market, pure = _market_prefix(code)
    secid = f"{'1' if market == 'sh' else '0'}.{pure}"
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid, "klt": "101", "fqt": "0",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "beg": "0", "end": "20500101", "lmt": str(limit),
    }
    resp = httpx.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    klines = (data.get("data") or {}).get("klines") or []
    records = []
    for line in klines:
        parts = line.split(",")
        records.append({
            "date": parts[0], "open": float(parts[1]), "close": float(parts[2]),
            "high": float(parts[3]), "low": float(parts[4]),
            "volume": float(parts[5]), "amount": float(parts[6]),
        })
    return records


# ---------- 链路 ----------

def get_daily(db: Session, code: str, limit: int = 120) -> dict:
    priority = [s.strip() for s in settings_svc.get(db, "market_priority").split(",") if s.strip()]
    errors: list[str] = []
    for source in priority:
        try:
            if source == "tdx":
                data = read_tdx_day(settings_svc.get(db, "tdx_path"), code, limit)
            elif source == "akshare":
                data = read_akshare(code, limit)
            elif source == "web":
                data = read_eastmoney(code, limit)
            else:
                continue
            if data:
                return {"source": source, "code": code, "klines": data}
        except Exception as exc:  # noqa: BLE001 - 逐源降级，任何异常都尝试下一源
            errors.append(f"{source}: {exc}")
    return {"source": None, "code": code, "klines": [], "errors": errors}


def market_context_text(db: Session, codes: list[str], day: date) -> str:
    """给 AI 打分用的行情上下文：大盘 + 涉及个股当日与近5日表现。"""
    lines: list[str] = []
    targets = [("000001.SH", "上证指数"), ("399001.SZ", "深证成指"), ("399006.SZ", "创业板指")]
    targets += [(c, "") for c in codes]
    day_str = day.isoformat()
    for code, label in targets:
        result = get_daily(db, code, limit=10)
        klines = result["klines"]
        if not klines:
            continue
        recent = [k for k in klines if k["date"] <= day_str][-6:]
        if not recent:
            continue
        today = recent[-1]
        change = ""
        if len(recent) >= 2:
            prev_close = recent[-2]["close"]
            if prev_close:
                change = f"，当日涨跌 {((today['close'] / prev_close) - 1) * 100:+.2f}%"
        seq = " -> ".join(f"{k['close']:.2f}" for k in recent)
        lines.append(f"{label or code}（{code}）近{len(recent)}日收盘: {seq}{change}")
    return "\n".join(lines) if lines else "（行情数据不可用）"
