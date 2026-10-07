from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.db.base import SessionLocal
from app.db.models import IndexDaily, Instrument, PriceDaily
from app.services import market, sectors


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


def test_rules_are_consistent():
    r = sectors.rules()
    assert all(ind in r["industries"] for s in r["sectors"].values() for ind in s["industries"])
    assert all(ind in r["industries"] for ind in r["companies"].values())
    assert all(sym == sym.upper() and " " not in sym for sym in r["companies"])
    # every tile on the dashboard opens a page, and the page's index is the tile's index
    assert {sym for sym, _ in market.SECTORS} <= set(sectors.tile_keys())
    assert sectors.industry_of("HDFCBANK") == "private_bank" and sectors.industry_of("NOSUCH") is None
    assert sectors.rules()["sectors"]["banks"]["industries"] == ["private_bank", "psu_bank"]


def test_sector_page_groups_tracked_companies_by_industry(signed_in, monkeypatch):
    monkeypatch.setattr(market, "market_open", lambda now=None: False)
    with SessionLocal() as db:
        _seed_stock(db, "HDFCBANK", list(np.linspace(1500, 1600, 259)) + [1620.0], 1)  # private bank, up 1.25% on the day
        _seed_stock(db, "SBIN", list(np.linspace(900, 800, 259)) + [790.0], 2)  # public-sector bank, down 1.25% on the day
        _seed_stock(db, "TCS", [4000.0] * 260, 3)  # IT: must not appear under banks
        _seed_stock(db, "ZZZNEW", [100.0] * 260, 4)  # not classified yet
        _seed_index(db, "BANKNIFTY", list(np.linspace(50000, 55000, 260)))
        db.commit()

    page = signed_in.get("/api/market/sectors/banks").json()
    assert page["label"] == "Banks" and page["index"]["name"] == "Nifty Bank" and page["index"]["last"] == 55000.0
    assert [g["label"] for g in page["groups"]] == ["Private banks", "Public-sector banks"]
    assert [c["symbol"] for g in page["groups"] for c in g["companies"]] == ["HDFCBANK", "SBIN"]
    assert page["summary"] == {
        "companies": 2,
        "advancers": 1,
        "decliners": 1,
        "unchanged": 0,
        "avg_change_pct": pytest.approx((page["groups"][0]["companies"][0]["change_pct"] + page["groups"][1]["companies"][0]["change_pct"]) / 2, abs=1e-4),
        "best": {"symbol": "HDFCBANK", "change_pct": page["groups"][0]["companies"][0]["change_pct"]},
        "worst": {"symbol": "SBIN", "change_pct": page["groups"][1]["companies"][0]["change_pct"]},
    }
    assert len(page["history"]) == 260 and page["history"][-1][1] == 55000.0 and page["checked"] == "2026-10-06"
    assert {o["key"] for o in page["others"]} >= {"it", "financials"} and "banks" not in {o["key"] for o in page["others"]}

    it = signed_in.get("/api/market/sectors/it").json()
    assert [c["symbol"] for g in it["groups"] for c in g["companies"]] == ["TCS"] and it["index"] is None and it["history"] == []

    industrials = signed_in.get("/api/market/sectors/industrials").json()
    assert industrials["groups"] == [] and industrials["summary"]["companies"] == 0

    assert signed_in.get("/api/market/sectors/nosuch").status_code == 404

    overview = signed_in.get("/api/market/sectors").json()
    banks = next(s for s in overview["sectors"] if s["key"] == "banks")
    assert banks["summary"]["companies"] == 2 and banks["index"]["symbol"] == "BANKNIFTY"
    assert overview["unclassified"] == ["ZZZNEW"] and overview["tracked"] == 4

    snap = signed_in.get("/api/market/snapshot").json()
    assert snap["sectors"][0] == snap["sectors"][0] | {"label": "Banks", "key": "banks"}
    assert [i["sector"] for i in snap["indices"]] == ["banks"]  # the Nifty Bank card links to the same page
