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


# ---------- 股票 / ETF 搜索 ----------

_stock_cache: list[dict[str, str]] | None = None
_etf_cache: list[dict[str, str]] | None = None


def _load_stock_list() -> list[dict[str, str]]:
    global _stock_cache
    if _stock_cache is not None:
        return _stock_cache
    try:
        import akshare as ak  # noqa: PLC0415

        df = ak.stock_info_a_code_name()
        _stock_cache = [
            {"code": str(row["code"]).zfill(6), "name": str(row["name"])}
            for _, row in df.iterrows()
        ]
    except Exception:  # noqa: BLE001
        _stock_cache = []
    return _stock_cache


def _load_etf_list() -> list[dict[str, str]]:
    global _etf_cache
    if _etf_cache is not None:
        return _etf_cache
    try:
        import akshare as ak  # noqa: PLC0415

        df = ak.fund_etf_spot_em()
        code_col = "代码" if "代码" in df.columns else "fund_code"
        name_col = "名称" if "名称" in df.columns else "name"
        _etf_cache = [
            {"code": str(row[code_col]).zfill(6), "name": str(row[name_col])}
            for _, row in df.iterrows()
        ]
    except Exception:  # noqa: BLE001
        _etf_cache = []
    return _etf_cache


def _all_securities() -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for item in _load_stock_list() + _load_etf_list():
        merged[item["code"]] = item
    return list(merged.values())


def lookup_by_code(code: str) -> dict[str, str] | None:
    """按 6 位 A 股 / ETF 代码精确查找。"""
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) != 6:
        return None
    target = digits.zfill(6)
    for item in _all_securities():
        if item["code"] == target:
            return item
    return None


# 券商 App 简称 → 标准代码（截图无 6 位代码时的兜底）
_OCR_NAME_TO_CODE: dict[str, str] = {
    "科半导体": "588710",
    "科创半导体": "588710",
    "科创半导体设备": "588710",
    "科创半导体etf": "588710",
    "科创半导体ETF": "588710",
    "科创板半导体": "588710",
    "科创板半导体etf": "588710",
    "科创板半导体ETF": "588710",
}

# akshare 未加载时的静态名称
_STATIC_CODE_NAME: dict[str, str] = {
    "588710": "科创半导体设备ETF华泰柏瑞",
    "515400": "大数据ETF富国",
}


def _is_etf_code(code: str) -> bool:
    return code.startswith(("51", "56", "58", "15", "16"))


def _normalize_query_name(name: str) -> str:
    return name.replace(" ", "").replace("　", "").strip()


def _strip_etf_suffix(name: str) -> str:
    s = _normalize_query_name(name)
    for w in ("ETF", "etf", "基金", "LOF", "联接"):
        s = s.replace(w, "")
    return s


def _subsequence_match(query: str, target: str) -> bool:
    """简称是否为全称的有序子序列（如「科半导体」⊂「科创半导体设备ETF」）。"""
    q = _strip_etf_suffix(query)
    if len(q) < 2:
        return False
    ti = 0
    for ch in target:
        if ti < len(q) and ch == q[ti]:
            ti += 1
    return ti == len(q)


def _implied_price(
    price: float | None,
    qty: int | None,
    market_value: float | None,
) -> float | None:
    if price is not None and price > 0:
        return price
    if qty is not None and qty > 0 and market_value is not None and market_value > 0:
        return market_value / qty
    return None


def _code_name_pair(code: str) -> tuple[str, str] | None:
    hit = lookup_by_code(code)
    if hit:
        return hit["code"], hit["name"]
    static = _STATIC_CODE_NAME.get(code)
    if static:
        return code, static
    return None


def _rank_name_candidates(name: str, pool: list[dict[str, str]]) -> list[tuple[int, dict[str, str]]]:
    q = _normalize_query_name(name)
    q_lower = q.lower()
    q_core = _strip_etf_suffix(name)
    ranked: list[tuple[int, dict[str, str]]] = []
    for item in pool:
        full = item["name"]
        full_norm = _normalize_query_name(full)
        full_lower = full_norm.lower()
        score = -1
        if full == name or full_norm == q or full_lower == q_lower:
            score = 200
        elif q_core and len(q_core) >= 2 and q_core in full_norm:
            score = 130 + min(len(q_core), 20)
        elif q and len(q) >= 2 and (q in full_norm or q_lower in full_lower):
            score = 110 + min(len(q), 15)
        elif q_core and len(q_core) >= 2 and _subsequence_match(q_core, full_norm):
            score = 85 + min(len(q_core), 15)
        elif q and len(q) >= 2 and _subsequence_match(q, full_norm):
            score = 75 + min(len(q), 12)
        if score >= 0:
            if _is_etf_code(item["code"]) and _etf_like_name(name):
                score += 8
            ranked.append((score, item))
    ranked.sort(key=lambda x: (-x[0], x[1]["code"]))
    return ranked


def _etf_like_name(name: str) -> bool:
    return any(k in name for k in ("ETF", "etf", "基金", "半导体", "科创", "指数", "LOF", "数据"))


def _collect_name_candidates(name: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    candidates: list[dict[str, str]] = []
    for hit in search_stocks(name, limit=15):
        if hit["code"] not in seen:
            seen.add(hit["code"])
            candidates.append(hit)
    q_core = _strip_etf_suffix(name)
    if len(q_core) <= 10:
        for item in _load_etf_list():
            if item["code"] in seen:
                continue
            if _subsequence_match(name, item["name"]) or (
                len(q_core) >= 2 and q_core in _normalize_query_name(item["name"])
            ):
                seen.add(item["code"])
                candidates.append(item)
    if len(q_core) <= 6:
        for item in _load_stock_list():
            if item["code"] in seen:
                continue
            if item["name"] == name or (len(q_core) >= 2 and q_core in item["name"]):
                seen.add(item["code"])
                candidates.append(item)
    return candidates


def _disambiguate_by_price(
    candidates: list[dict[str, str]],
    implied: float,
    db: Session,
) -> dict[str, str] | None:
    best_item: dict[str, str] | None = None
    best_err = float("inf")
    for item in candidates[:12]:
        try:
            klines = get_daily(db, item["code"], limit=8)["klines"]
            if not klines:
                continue
            close = float(klines[-1]["close"])
            if close <= 0:
                continue
            err = abs(close - implied) / implied
            if err < best_err:
                best_err = err
                best_item = item
        except Exception:  # noqa: BLE001
            continue
    if best_item is not None and best_err < 0.25:
        return best_item
    return None


def resolve_stock(
    code: str,
    name: str,
    *,
    price: float | None = None,
    market_value: float | None = None,
    qty: int | None = None,
    db: Session | None = None,
) -> tuple[str, str]:
    """从 OCR/手输的代码或名称解析为标准 6 位代码与名称。

    券商截图常只有简称（如「科半导体」），与基金全称不是子串关系；
    采用子序列匹配 + 行情价格消歧，不确定时留空 code 避免误匹配。
    """
    code = (code or "").strip()
    name = (name or "").strip()
    digits = "".join(ch for ch in code if ch.isdigit())

    if len(digits) == 6:
        pair = _code_name_pair(digits.zfill(6))
        if pair:
            return pair

    if not digits and name:
        alias_key = _normalize_query_name(name)
        alias_code = _OCR_NAME_TO_CODE.get(name) or _OCR_NAME_TO_CODE.get(alias_key)
        if alias_code:
            pair = _code_name_pair(alias_code)
            if pair:
                return pair

    if name:
        candidates = _collect_name_candidates(name)
        ranked = _rank_name_candidates(name, candidates)
        if ranked:
            top_score = ranked[0][0]
            top_group = [item for sc, item in ranked if sc >= top_score - 5][:8]
            implied = _implied_price(price, qty, market_value)

            if db is not None and implied is not None and len(top_group) > 1:
                picked = _disambiguate_by_price(top_group, implied, db)
                if picked:
                    return picked["code"], picked["name"]

            if len(top_group) == 1:
                return top_group[0]["code"], top_group[0]["name"]

            if len(ranked) >= 2 and ranked[0][0] - ranked[1][0] >= 18:
                return ranked[0][1]["code"], ranked[0][1]["name"]

            if top_score >= 130:
                return ranked[0][1]["code"], ranked[0]["name"]

            # 多个候选分数接近：不强行匹配，保留简称供用户手选
            return "", name

    if digits:
        hits = search_stocks(digits, limit=3)
        if hits and hits[0]["code"] == digits.zfill(6):
            return hits[0]["code"], hits[0]["name"]

    if len(digits) == 6:
        return digits.zfill(6), name
    return code, name


def search_stocks(query: str, limit: int = 12) -> list[dict[str, str]]:
    """按代码或名称模糊匹配 A 股 / ETF 列表。"""
    q = query.strip()
    if not q:
        return []
    stocks = _all_securities()
    q_lower = q.lower()
    q_digits = "".join(ch for ch in q if ch.isdigit())
    q_norm = _normalize_query_name(q)
    q_core = _strip_etf_suffix(q)

    scored: list[tuple[int, dict[str, str]]] = []
    for item in stocks:
        code, name = item["code"], item["name"]
        name_norm = _normalize_query_name(name)
        score = -1
        if q_digits and code == q_digits.zfill(6):
            score = 100
        elif q_digits and code.startswith(q_digits):
            score = 80 - len(code)
        elif q_norm and len(q_norm) >= 2 and q_norm in name_norm:
            score = 70 + min(len(q_norm), 15)
        elif q_lower in name.lower():
            score = 60
        elif q_core and len(q_core) >= 2 and _subsequence_match(q_core, name_norm):
            score = 52 + min(len(q_core), 12)
        elif q_lower in code:
            score = 50
        if score >= 0:
            scored.append((score, item))

    scored.sort(key=lambda x: (-x[0], x[1]["code"]))
    seen: set[str] = set()
    results: list[dict[str, str]] = []
    for _, item in scored:
        if item["code"] in seen:
            continue
        seen.add(item["code"])
        results.append(item)
        if len(results) >= limit:
            break
    return results


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
