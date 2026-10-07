from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, IntegrityError

from app.connectors.groww import Candle, GrowwNoDataAccess
from app.connectors.http import SourceUnavailable
from app.db.base import SessionLocal, utcnow
from app.db.models import IndexDaily, Instrument, PaperTrade, PriceDaily, Recommendation, SetupBacktest, StrategyVersion
from app.engines.setups import Signal
from app.services import groww_service, stock_data
from app.services import trading as svc
from tests.conftest import CSRF


def _sessions(n: int, end: date) -> list[date]:
    days, d = [], end
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


LAST = _sessions(1, utcnow().date() - timedelta(days=1))[0]  # the most recent weekday before today


def seed(db, symbol="TESTCO", n=260, end=LAST, price=500.0, seed_=1) -> Instrument:
    inst = Instrument(symbol=symbol, groww_symbol=f"NSE-{symbol}", name=f"{symbol} Ltd", series="EQ", in_universe=True, universe_rank=1)
    db.add(inst)
    db.flush()
    rng = np.random.default_rng(seed_)
    closes = price * np.cumprod(1 + rng.normal(0.0005, 0.012, n))
    for d, c in zip(_sessions(n, end), closes):
        db.add(PriceDaily(instrument_id=inst.id, date=d, open=c * 0.998, high=c * 1.01, low=c * 0.99, close=c, volume=100000))
        db.merge(IndexDaily(symbol="NIFTY", date=d, open=1, high=1, low=1, close=1))
    inst.history_start, inst.history_end = _sessions(n, end)[0], end
    db.commit()
    return inst


def allow_setups(db, avg_r=0.25):
    v = StrategyVersion(engine="swing", version=1, config_hash="t" * 16, config_json={})
    db.add(v)
    db.flush()
    stats = {"trades": 400, "win_rate": 0.45, "avg_r": avg_r, "max_losing_streak": 7, "period": ["2020-01-01", "2026-09-01"]}
    for s in ("trend_pullback", "volume_breakout"):
        db.add(SetupBacktest(setup=s, strategy_version_id=v.id, capital=10000, universe_size=1, stats_json=stats, allowed=True, verdict="ok"))
    db.commit()


@pytest.fixture
def fake_signal(monkeypatch):
    def fake(ind, rules, only_last_day=False):
        last = ind.iloc[-1]
        c = float(last.close)
        return [Signal("volume_breakout", ind.index[-1].date(), c, c, round(c * 1.01, 2), round(c * 0.97, 2), round(c * 1.01 + 2.5 * (c * 1.01 - c * 0.97), 2), 15, ["why"])]

    monkeypatch.setattr(svc, "find_signals", fake)


def test_no_ideas_until_a_setup_passes_its_backtest(fake_signal):
    with SessionLocal() as db:
        seed(db)
        msg = svc.generate_ideas(db)
        assert "passed its backtest" in msg
        assert db.query(Recommendation).count() == 0


def test_ideas_are_sized_explained_and_idempotent(fake_signal):
    with SessionLocal() as db:
        seed(db)
        allow_setups(db)
        msg = svc.generate_ideas(db)
        assert "1 idea" in msg
        rec = db.query(Recommendation).one()
        assert rec.is_paper and rec.status == "open" and rec.for_session == svc.next_session(LAST)
        # R-05: ₹100 risk (1% of ₹10,000); also ≤ 35% of capital in one trade
        per_share = rec.entry_high - rec.stop_loss
        assert rec.qty == min(int(100 // per_share), int(3500 // rec.entry_high))
        assert rec.rationale_json["charges"] > 0 and rec.rationale_json["reward_risk"] >= 2
        assert any("Delivery" in s for s in rec.groww_steps_json) and len(rec.risks_json) == 4
        assert "already made" in svc.generate_ideas(db)


def test_stale_prices_mean_no_ideas(fake_signal):
    with SessionLocal() as db:
        seed(db, end=LAST - timedelta(days=12))
        allow_setups(db)
        with pytest.raises(SourceUnavailable):
            svc.generate_ideas(db)


def _add_bar(db, inst, d, o, h, lo, c):
    db.add(PriceDaily(instrument_id=inst.id, date=d, open=o, high=h, low=lo, close=c, volume=100000))
    db.merge(IndexDaily(symbol="NIFTY", date=d, open=1, high=1, low=1, close=1))
    db.commit()


def _idea(db, fake_signal_fixture=None):
    inst = seed(db)
    allow_setups(db)
    svc.generate_ideas(db)
    return inst, db.query(Recommendation).one()


def test_paper_trade_life_cycle_target(fake_signal):
    with SessionLocal() as db:
        inst, rec = _idea(db)
        t = svc.place_paper_trade(db, rec.id, rec.qty)
        assert t.status == "pending" and rec.status == "taken"
        s1 = rec.for_session
        _add_bar(db, inst, s1, rec.entry_high * 0.999, rec.entry_high * 1.01, rec.entry_high * 0.99, rec.entry_high)
        _add_bar(db, inst, svc.next_session(s1), rec.entry_high, rec.target + 1, rec.entry_high, rec.target)
        assert "1 bought" in svc.process_paper(db)
        db.refresh(t)
        assert t.status == "closed" and t.exit_reason == "target" and t.net_pnl > 0 and t.charges_json["total"] > 0
        s = svc.paper_summary(db)
        assert s["closed_trades"] == 1 and s["win_rate"] == 1.0 and s["realized_pnl"] == t.net_pnl
        svc.process_paper(db)  # idempotent
        db.refresh(t)
        assert t.status == "closed"


def test_paper_trade_missed_on_gap_up(fake_signal):
    with SessionLocal() as db:
        inst, rec = _idea(db)
        t = svc.place_paper_trade(db, rec.id, 1)
        _add_bar(db, inst, rec.for_session, rec.entry_high * 1.03, rec.entry_high * 1.05, rec.entry_high * 1.02, rec.entry_high * 1.04)
        svc.process_paper(db)
        db.refresh(t)
        assert t.status == "missed"


def test_quantity_cap_and_position_limit(fake_signal):
    with SessionLocal() as db:
        inst, rec = _idea(db)
        with pytest.raises(svc.TradingBlocked, match="R-05"):
            svc.place_paper_trade(db, rec.id, rec.qty + 1)
        svc.place_paper_trade(db, rec.id, 1)
        with pytest.raises(svc.TradingBlocked, match="already taken"):
            svc.place_paper_trade(db, rec.id, 1)


def _closed_loss(db, inst, acct_id, day, pnl=-50.0):
    db.add(PaperTrade(account_id=acct_id, instrument_id=inst.id, status="closed", qty=1, entry_low=1, entry_high=1, stop=0.9, target=2,
                      max_hold_days=10, for_session=day, entry_date=day, entry_price=1, exit_date=day, exit_price=0.9, exit_reason="stop",
                      net_pnl=pnl, r_multiple=-1.1))


def test_cooling_off_after_three_losses(fake_signal):
    with SessionLocal() as db:
        inst = seed(db)
        allow_setups(db)
        acct = svc.account(db)
        for _ in range(3):
            _closed_loss(db, inst, acct.id, LAST)
        db.commit()
        st = svc.state(db)
        assert st["cooling_off_until"] and "R-10" in st["cooling_off_reason"]
        assert "R-10" in svc.generate_ideas(db)
        assert db.query(Recommendation).count() == 0


def test_daily_loss_limit(fake_signal):
    with SessionLocal() as db:
        inst = seed(db)
        acct = svc.account(db)
        _closed_loss(db, inst, acct.id, LAST, pnl=-350.0)  # 3.5% of ₹10,000
        db.commit()
        st = svc.state(db)
        assert st["loss_limit_hit"] and "R-06" in st["loss_limit_reason"]


def test_recommendations_cannot_be_deleted_or_rewritten(fake_signal):
    with SessionLocal() as db:
        _, rec = _idea(db)
        with pytest.raises((IntegrityError, DatabaseError)):
            db.execute(text("DELETE FROM recommendations"))
        db.rollback()
        with pytest.raises((IntegrityError, DatabaseError)):
            db.execute(text("UPDATE recommendations SET stop_loss = stop_loss - 1"))
        db.rollback()
        db.execute(text("UPDATE recommendations SET status = 'expired'"))  # status may change
        db.commit()


def test_backtests_run_on_stored_history():
    with SessionLocal() as db:
        for i in range(3):
            seed(db, symbol=f"S{i}", n=700, seed_=i + 10)
        msg = svc.run_backtests(db)
        rows = db.query(SetupBacktest).all()
        assert {r.setup for r in rows} == {"trend_pullback", "volume_breakout"}
        assert all(not r.allowed for r in rows)  # far fewer than 100 trades on 3 synthetic stocks
        assert "OFF" in msg


class FakeGroww:
    def __init__(self, forbidden=False):
        self.forbidden = forbidden

    def daily_candles(self, symbol, start, end):
        if self.forbidden:
            raise GrowwNoDataAccess("plan lacks market data")
        price = 150.0 if symbol != "NSE-CHEAP" else 50.0
        vol = 5_000_000 if symbol == "NSE-BIG" else 2_000_000
        return [Candle(d, price, price * 1.01, price * 0.99, price, vol) for d in _sessions(80, LAST) if start <= d <= end]


def test_universe_scan_ranks_by_liquidity(monkeypatch):
    with SessionLocal() as db:
        for sym in ("BIG", "SMALL", "CHEAP", "NIFTYBEES"):
            db.add(Instrument(symbol=sym, groww_symbol=f"NSE-{sym}", name=f"{sym} {'ETF' if sym == 'NIFTYBEES' else 'Ltd'}", series="EQ"))
        db.commit()
        monkeypatch.setattr(groww_service, "client", lambda db: FakeGroww())
        stock_data.scan_universe(db)
        uni = {i.symbol: i for i in db.query(Instrument).all()}
        assert uni["BIG"].in_universe and uni["BIG"].universe_rank == 1
        assert uni["SMALL"].in_universe  # ₹150 × 20 lakh = ₹30 cr a day
        assert not uni["CHEAP"].in_universe  # below ₹100
        assert not uni["NIFTYBEES"].in_universe  # ETF excluded by name


class ShortThenFull(FakeGroww):
    """First answer for BIG is cut short (a Groww hiccup); the second is complete."""

    def __init__(self):
        super().__init__()
        self.seen = set()

    def daily_candles(self, symbol, start, end):
        full = super().daily_candles(symbol, start, end)
        if symbol == "NSE-BIG" and symbol not in self.seen:
            self.seen.add(symbol)
            return full[-1:]
        return full


def test_short_answers_get_a_second_look(monkeypatch):
    with SessionLocal() as db:
        for sym in ("BIG", "SMALL"):
            db.add(Instrument(symbol=sym, groww_symbol=f"NSE-{sym}", name=f"{sym} Ltd", series="EQ"))
        db.commit()
        monkeypatch.setattr(groww_service, "client", lambda db: ShortThenFull())
        msg = stock_data.scan_universe(db)
        assert "1 needed a second look" in msg
        assert db.query(Instrument).filter_by(symbol="BIG").one().universe_rank == 1


def test_groww_busy_stops_the_scan(monkeypatch):
    from app.connectors.groww import GrowwBusy

    class Busy(FakeGroww):
        def daily_candles(self, *a):
            raise GrowwBusy("rate limited")

    with SessionLocal() as db:
        db.add(Instrument(symbol="BIG", groww_symbol="NSE-BIG", name="Big Ltd", series="EQ"))
        db.commit()
        monkeypatch.setattr(groww_service, "client", lambda db: Busy())
        with pytest.raises(GrowwBusy):
            stock_data.scan_universe(db)


def test_no_market_data_fails_fast(monkeypatch):
    with SessionLocal() as db:
        db.add(Instrument(symbol="BIG", groww_symbol="NSE-BIG", name="Big Ltd", series="EQ"))
        db.commit()
        monkeypatch.setattr(groww_service, "client", lambda db: FakeGroww(forbidden=True))
        with pytest.raises(GrowwNoDataAccess):
            stock_data.scan_universe(db)


def test_trading_api(signed_in, fake_signal, monkeypatch):
    with SessionLocal() as db:
        _idea(db)
    ov = signed_in.get("/api/trading/overview").json()
    assert ov["state"]["capital"] == 10000 and ov["ideas_status"]["count"] == 1
    assert any("practice" in r.lower() or "paper" in r.lower() for r in ov["real_money_locked"])
    ideas = signed_in.get("/api/trading/ideas").json()
    assert len(ideas) == 1 and ideas[0]["symbol"] == "TESTCO" and ideas[0]["groww_steps"]
    r = signed_in.post(f"/api/trading/ideas/{ideas[0]['id']}/paper-buy", json={"qty": 999}, headers=CSRF)
    assert r.status_code == 409 and "R-05" in r.json()["detail"]
    assert signed_in.post(f"/api/trading/ideas/{ideas[0]['id']}/paper-buy", json={"qty": 1}, headers=CSRF).status_code == 200
    paper = signed_in.get("/api/trading/paper").json()
    assert paper["trades"][0]["status"] == "pending"
    tid = paper["trades"][0]["id"]
    assert signed_in.post(f"/api/trading/paper/{tid}/cancel", headers=CSRF).json()["ok"]
    bts = signed_in.get("/api/trading/backtests").json()
    assert {b["setup"] for b in bts} == {"trend_pullback", "volume_breakout"} and all(b["allowed"] for b in bts)
    assert signed_in.patch("/api/settings", json={"trading_paper_capital": 500}, headers=CSRF).status_code == 400
    assert signed_in.patch("/api/settings", json={"trading_paper_capital": 25000}, headers=CSRF).status_code == 200
    monkeypatch.setattr(groww_service, "diagnose", lambda db: {"auth_method": "secret", "login": {"ok": True, "detail": "x"}, "portfolio": None, "prices": {"ok": False, "detail": "no"}, "history": None})
    assert signed_in.post("/api/trading/groww-check", headers=CSRF).json()["prices"]["ok"] is False
