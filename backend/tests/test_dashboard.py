import numpy as np
import pandas as pd

from app.db.base import SessionLocal
from app.db.models import IndexDaily, MfSchemeFacts, User
from app.services import dashboard, mf_scores
from tests.test_mf_engine import universe  # noqa: F401 — fixture reuse


def _index(db, symbol, closes):
    days = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=len(closes))
    db.add_all(IndexDaily(symbol=symbol, date=d.date(), open=c, high=c, low=c, close=c) for d, c in zip(days, closes))
    db.commit()


def test_dashboard_needs_login(client):
    assert client.get("/api/dashboard").status_code == 401


def test_dashboard_before_any_data(signed_in):
    d = signed_in.get("/api/dashboard").json()
    assert d["market"] is None
    assert [h["key"] for h in d["horizons"]] == ["m3", "m6", "y1", "y2", "y3", "y5"]
    assert all(h["picks"] == [] for h in d["horizons"])


def test_market_mood_reads_trend_and_vix():
    with SessionLocal() as db:
        _index(db, "NIFTY", list(np.linspace(20000, 26000, 300)))
        _index(db, "INDIAVIX", [12.0] * 20)
        m = dashboard.market(db)
        assert m["mood"] == "Positive" and "above its 200-day average" in m["reason"] and "calm" in m["reason"]
        assert 120 <= len(m["chart"]) <= 135  # six months of sessions
        db.query(IndexDaily).filter_by(symbol="INDIAVIX").delete()
        db.commit()
        _index(db, "INDIAVIX", [24.0] * 20)
        assert dashboard.market(db)["mood"] == "Mixed"  # uptrend, but the market is nervous
        db.query(IndexDaily).delete()
        db.commit()
        _index(db, "NIFTY", list(np.linspace(26000, 20000, 300)))
        assert dashboard.market(db)["mood"] == "Weak"


def test_market_needs_a_year_of_history():
    with SessionLocal() as db:
        _index(db, "NIFTY", [20000.0] * 100)
        assert dashboard.market(db) is None


def test_horizon_picks_follow_the_rules(universe, signed_in):  # noqa: F811
    with SessionLocal() as db:
        mf_scores.run_scoring(db)
        db.get(MfSchemeFacts, {"scheme_code": 3005, "as_of": pd.Timestamp("2026-09-01").date()}).fee = 0.0002
        db.commit()
        picks = {h["key"]: h for h in dashboard.horizon_picks(db, db.query(User).one())}
    three = picks["m3"]["picks"]
    assert [p["category"] for p in three] == ["Liquid Fund"]  # no overnight funds in this test universe
    assert picks["y1"]["picks"] == []  # no money-market / arbitrage funds here: nothing is invented
    assert [p["category"] for p in picks["y3"]["picks"]] == ["Balanced Advantage", "Short Duration Fund"]  # moderate (no profile yet)
    assert [p["category"] for p in picks["y5"]["picks"]] == ["Nifty 50 index fund", "Flexi Cap Fund"]
    assert picks["y5"]["picks"][1]["scheme_code"] == 1005
    liquid = next(p for p in three if p["category"] == "Liquid Fund")
    assert liquid["ter"] is not None and liquid["typical_1y"] is not None
    if liquid["scheme_code"] == 3005:
        assert liquid["fee"] == 0.0002
    # nothing in shares for money needed within a year
    for key in ("m3", "m6", "y1", "y2"):
        assert all(p["category"] not in ("Flexi Cap Fund", "Nifty 50 index fund", "Balanced Advantage") for p in picks[key]["picks"])

