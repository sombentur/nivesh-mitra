from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.db.base import SessionLocal
from app.db.models import IndexDaily, Instrument, PriceDaily
from app.services import market


@pytest.fixture(autouse=True)
def fresh_cache():
    market.reset_cache()
    yield
    market.reset_cache()


def _seed_stock(db, symbol, closes, rank):
    inst = Instrument(symbol=symbol, groww_symbol=f"NSE-{symbol}", name=f"{symbol} LTD", in_universe=True, universe_rank=rank)
    db.add(inst)
    db.flush()
    days = pd.bdate_range(end=pd.Timestamp(date.today() - timedelta(days=1)), periods=len(closes))
    db.add_all(PriceDaily(instrument_id=inst.id, date=d.date(), open=c, high=c * 1.01, low=c * 0.99, close=c, volume=100000) for d, c in zip(days, closes))


def _seed_index(db, symbol, closes):
    days = pd.bdate_range(end=pd.Timestamp(date.today() - timedelta(days=1)), periods=len(closes))
    db.add_all(IndexDaily(symbol=symbol, date=d.date(), open=c, high=c, low=c, close=c) for d, c in zip(days, closes))


def test_snapshot_lists_breadth_and_indices(signed_in, monkeypatch):
    monkeypatch.setattr(market, "market_open", lambda now=None: False)
    with SessionLocal() as db:
        _seed_stock(db, "RISER", list(np.linspace(100, 200, 260)), 1)  # steady uptrend, at its high
        _seed_stock(db, "FALLER", list(np.linspace(200, 100, 260)), 2)
        _seed_stock(db, "FLAT", [500.0] * 260, 3)
        _seed_index(db, "NIFTY", list(np.linspace(20000, 22000, 260)))
        _seed_index(db, "NIFTYIT", [30000.0] * 258 + [30300.0, 30000.0])
        db.commit()
    s = signed_in.get("/api/market/snapshot").json()
    assert [i["label"] for i in s["indices"]] == ["Nifty 50", "Nifty IT"]
    assert s["sectors"][0]["label"] == "IT" and s["sectors"][0]["change_pct"] == pytest.approx(-0.0099, abs=1e-4)
    riser, faller, flat = (s["stocks"][k] for k in ("RISER", "FALLER", "FLAT"))
    assert riser["trend"] == "Uptrend" and faller["trend"] == "Downtrend"
    assert flat["ret_3m"] == pytest.approx(0.0) and flat["from_high"] == pytest.approx(-0.0099, abs=1e-3)
    assert s["lists"]["leaders"] == ["RISER"] and s["lists"]["gainers"][0] == "RISER" and s["lists"]["losers"][0] == "FALLER"
    assert s["breadth"]["total"] == 3 and s["breadth"]["advancers"] == 1 and s["breadth"]["decliners"] == 1
    assert len(riser["spark"]) == 30 and riser["name"] == "Riser Ltd"
    t = signed_in.get("/api/market/ticker").json()
    assert [i["kind"] for i in t["nse"][:2]] == ["index", "index"] and {i["symbol"] for i in t["nse"]} >= {"RISER", "NIFTY"}


def test_live_prices_extend_the_series_during_market_hours(monkeypatch):
    monkeypatch.setattr(market, "market_open", lambda now=None: True)

    class Live:
        def ltp(self, keys):
            return {"NSE_RISER": 210.0, "NSE_NIFTY": 22100.0}

    monkeypatch.setattr(market.groww_service, "client", lambda db: Live())
    with SessionLocal() as db:
        _seed_stock(db, "RISER", list(np.linspace(100, 200, 260)), 1)
        _seed_index(db, "NIFTY", list(np.linspace(20000, 22000, 260)))
        db.commit()
        s = market.snapshot(db)
    assert s["live"] is True
    r = s["stocks"]["RISER"]
    assert r["last"] == 210.0 and r["prev"] == 200.0 and r["change_pct"] == pytest.approx(0.05) and r["spark"][-1] == 210.0
    assert s["indices"][0]["last"] == 22100.0


def test_market_hours():
    ist = market.IST
    assert market.market_open(datetime(2026, 9, 30, 10, 0, tzinfo=ist))
    assert not market.market_open(datetime(2026, 9, 30, 16, 0, tzinfo=ist))
    assert not market.market_open(datetime(2026, 10, 3, 10, 0, tzinfo=ist))  # Saturday
    assert not market.market_open(datetime(2026, 10, 2, 10, 0, tzinfo=ist))  # Friday, but Gandhi Jayanti


def test_market_needs_login(client):
    assert client.get("/api/market/snapshot").status_code == 401
    assert client.get("/api/market/ticker").status_code == 401


def test_ticker_runs_nse_then_bse_then_stocks_with_live_sensex(monkeypatch):
    monkeypatch.setattr(market, "market_open", lambda now=None: True)
    asked = []

    class Live:
        def ltp(self, keys):
            asked.extend(keys)
            return {"NSE_NIFTY": 22100.0, "BSE_SENSEX": 72600.0, "NSE_RISER": 201.0}

    monkeypatch.setattr(market.groww_service, "client", lambda db: Live())
    with SessionLocal() as db:
        _seed_stock(db, "RISER", list(np.linspace(100, 200, 260)), 1)
        _seed_index(db, "NIFTY", list(np.linspace(20000, 22000, 260)))
        _seed_index(db, "SENSEX", list(np.linspace(70000, 72480, 260)))
        _seed_index(db, "BANKEX", [60000.0] * 260)
        db.commit()
        t = market.ticker(db)
    assert "BSE_SENSEX" in asked and "NSE_SENSEX" not in asked and "NSE_NIFTY" in asked
    assert [(i["symbol"], i["kind"]) for i in t["nse"]] == [("NIFTY", "index"), ("RISER", "stock")]
    assert [i["symbol"] for i in t["bse"]] == ["SENSEX", "BANKEX"]
    assert t["bse"][0]["label"] == "Sensex" and t["bse"][0]["last"] == 72600.0 and t["nse"][1]["last"] == 201.0


def test_bse_tape_uses_bse_prices(monkeypatch):
    monkeypatch.setattr(market, "market_open", lambda now=None: True)

    class Live:
        def ltp(self, keys):
            return {"NSE_RISER": 201.0, "BSE_RISER": 201.4}

    monkeypatch.setattr(market.groww_service, "client", lambda db: Live())
    with SessionLocal() as db:
        _seed_stock(db, "RISER", list(np.linspace(100, 200, 260)), 1)
        _seed_index(db, "BSE:RISER", [199.0, 200.2])
        db.commit()
        t = market.ticker(db)
    nse_riser = next(i for i in t["nse"] if i["symbol"] == "RISER")
    bse_riser = next(i for i in t["bse"] if i["symbol"] == "RISER")
    assert nse_riser["last"] == 201.0 and bse_riser["last"] == 201.4  # each exchange's own price
    assert bse_riser["change_pct"] == pytest.approx(201.4 / 200.2 - 1, abs=1e-4)
