"""核心逻辑单元测试。"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import CapitalFlow, Snapshot, Trade
from app.routers.reviews import _normalize_ai_trade_items, _normalize_dim_scores
from app.services import fees, netvalue
from app.services.market import _tdx_price_scale, read_tdx_day
import struct
from pathlib import Path
import tempfile


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_tdx_price_scale():
    assert _tdx_price_scale("600000") == 100.0
    assert _tdx_price_scale("588710") == 1000.0
    assert _tdx_price_scale("515400") == 1000.0
    assert _tdx_price_scale("159915") == 1000.0


def test_read_tdx_day_etf_divisor():
    with tempfile.TemporaryDirectory() as tmp:
        vipdoc = Path(tmp)
        path = vipdoc / "sh" / "lday"
        path.mkdir(parents=True)
        # raw close 1038 -> 1.038 for ETF
        chunk = struct.pack("<IIIIIfII", 20260710, 1026, 1026, 1026, 1038, 0.0, 100, 0)
        (path / "sh516000.day").write_bytes(chunk)
        rows = read_tdx_day(str(vipdoc), "516000", limit=1)
        assert len(rows) == 1
        assert abs(rows[0]["close"] - 1.038) < 0.001


def test_nav_initial_snapshot(db):
    db.add(CapitalFlow(flow_date=date(2026, 1, 2), kind="initial", amount=100_000))
    db.add(Snapshot(snap_date=date(2026, 1, 2), total_assets=100_000))
    db.commit()
    points = netvalue.build_series(db)
    assert len(points) == 1
    assert abs(points[0].nav - 1.0) < 1e-6
    assert points[0].assets == 100_000


def test_nav_grows_with_profit(db):
    db.add(CapitalFlow(flow_date=date(2026, 1, 2), kind="initial", amount=100_000))
    db.add(Snapshot(snap_date=date(2026, 1, 2), total_assets=100_000))
    db.add(Snapshot(snap_date=date(2026, 1, 3), total_assets=110_000))
    db.commit()
    points = netvalue.build_series(db)
    assert len(points) == 2
    assert abs(points[1].nav - 1.1) < 1e-4


def test_compute_fees_buy(db):
    f = fees.compute_fees(db, "buy", 10.0, 1000)
    assert f["fee_commission"] >= 5.0
    assert f["fee_stamp"] == 0.0


def test_compute_fees_sell_has_stamp(db):
    f = fees.compute_fees(db, "sell", 10.0, 1000)
    assert f["fee_stamp"] > 0


def test_normalize_dim_scores_aliases():
    out = _normalize_dim_scores({"仓位控制": 8, "entry": {"score": 7, "comment": "ok"}})
    assert out["position"]["score"] == 8
    assert out["entry"]["score"] == 7


def test_normalize_ai_trade_items_flat():
    result = {"position": 6, "summary": "test", "daily_summary": "x"}
    items = _normalize_ai_trade_items(result, [42])
    assert len(items) == 1
    assert items[0]["id"] == 42
    assert items[0]["scores"]["position"]["score"] == 6


def test_rounds_touching_day(db):
    from app.services import rounds as rounds_svc

    db.add(Trade(
        trade_date=date(2026, 1, 2), code="600000", name="浦发银行",
        side="buy", price=10.0, qty=100,
        fee_commission=5, fee_stamp=0, fee_transfer=0,
    ))
    db.add(Trade(
        trade_date=date(2026, 1, 5), code="600000", name="浦发银行",
        side="sell", price=11.0, qty=100,
        fee_commission=5, fee_stamp=0, fee_transfer=0,
    ))
    db.commit()
    all_rounds = rounds_svc.build_rounds(db)
    touching = rounds_svc.rounds_touching_day(all_rounds, date(2026, 1, 5))
    assert len(touching) == 1
    assert touching[0]["status"] == "closed"
    assert touching[0]["end_date"] == "2026-01-05"


def test_round_trip_trade_affects_estimate(db):
    from app.services import capital_estimate as cap_est

    db.add(CapitalFlow(flow_date=date(2026, 1, 1), kind="initial", amount=50_000))
    db.add(Trade(
        trade_date=date(2026, 1, 2), code="600000", name="浦发银行",
        side="buy", price=10.0, qty=100,
        fee_commission=5, fee_stamp=0, fee_transfer=0,
    ))
    db.commit()
    est = cap_est.estimate_snapshot(db, date(2026, 1, 2))
    assert est["ok"] is True
    assert est["cash"] < 50_000
