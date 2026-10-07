import json
import shutil
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from app import scheduler
from app.connectors.groww import IntradayBar
from app.db.base import SessionLocal
from app.db.models import IndexDaily, Instrument, JobRun, PriceDaily
from app.engines import holidays
from app.services import day_strip, intraday_data, intraday_practice, market_calendar, refresh, stock_data
from app.services.stock_data import IST
from tests.conftest import CSRF


@pytest.fixture(autouse=True)
def empty_intraday_folder():
    shutil.rmtree(intraday_data.folder(), ignore_errors=True)
    yield


def _at(monkeypatch, when: datetime):
    now = when.replace(tzinfo=IST)
    for module in (stock_data, day_strip, refresh, market_calendar):
        monkeypatch.setattr(module, "now_ist", lambda: now)


def test_previous_and_last_completed_sessions_skip_holidays():
    assert holidays.prev_trading_day(date(2026, 10, 5)) == date(2026, 10, 1)  # Monday → Thursday (Friday was a holiday)
    assert holidays.prev_trading_day(date(2026, 10, 3)) == date(2026, 10, 1)
    sat_noon = datetime(2026, 10, 3, 12, 0, tzinfo=IST)
    assert holidays.last_completed_session(sat_noon) == date(2026, 10, 1)
    assert holidays.last_completed_session(datetime(2026, 10, 5, 11, 0, tzinfo=IST)) == date(2026, 10, 1)  # Monday, market still open
    assert holidays.last_completed_session(datetime(2026, 10, 5, 15, 45, tzinfo=IST)) == date(2026, 10, 5)
    assert holidays.closed_reason(date(2026, 10, 2)) == "Mahatma Gandhi Jayanti" and holidays.closed_reason(date(2026, 10, 4)) == "Weekend"
    assert holidays.closed_reason(date(2026, 10, 5)) is None


# ------------------------------------------------------------------ a small market: sessions up to Thu 1 Oct 2026
SESSIONS = [d.date() for d in pd.bdate_range("2026-06-01", "2026-10-01") if holidays.is_trading_day(d.date())]


def _seed_market(db, nifty_last: float):
    """Nifty flat at 100 then `nifty_last` on the final day. STRONG closes at its high in an uptrend; WEAK falls."""
    for i, d in enumerate(SESSIONS):
        close = nifty_last if d == SESSIONS[-1] else 100.0
        db.add(IndexDaily(symbol="NIFTY", date=d, open=close, high=close, low=close, close=close))
        db.add(IndexDaily(symbol="SENSEX", date=d, open=close * 3, high=close * 3, low=close * 3, close=close * 3))
    strong = Instrument(symbol="STRONG", groww_symbol="NSE-STRONG", name="Strong Ltd", in_universe=True, universe_rank=1)
    weak = Instrument(symbol="WEAK", groww_symbol="NSE-WEAK", name="Weak Ltd", in_universe=True, universe_rank=2)
    pricey = Instrument(symbol="PRICEY", groww_symbol="NSE-PRICEY", name="Pricey Ltd", in_universe=True, universe_rank=3)
    db.add_all([strong, weak, pricey])
    db.flush()
    for i, d in enumerate(SESSIONS):
        up = 200.0 + i  # rises ₹1 a day, closing at the day's high
        db.add(PriceDaily(instrument_id=strong.id, date=d, open=up - 1, high=up, low=up - 2, close=up, volume=500000))
        down = 400.0 - i
        db.add(PriceDaily(instrument_id=weak.id, date=d, open=down + 1, high=down + 2, low=down, close=down, volume=300000))
        big = 20000.0 + 20 * i  # one share risks ₹240: more than the ₹100 allowed on a ₹10,000 practice account
        db.add(PriceDaily(instrument_id=pricey.id, date=d, open=big - 20, high=big, low=big - 40, close=big, volume=1000))
    db.commit()


def test_plan_stands_aside_below_the_average_and_lists_what_to_watch():
    with SessionLocal() as db:
        _seed_market(db, nifty_last=95.0)
        plan = intraday_practice.build_plan(db, date(2026, 10, 5))
    assert plan["session"] == "2026-10-05" and plan["based_on"] == "2026-10-01"
    assert plan["verdict"] == "stand_aside" and plan["filter"]["ok"] is False and plan["filter"]["average"] == pytest.approx(99.9)
    assert [w["symbol"] for w in plan["watchlist"]] == ["STRONG"]  # WEAK is in a downtrend; PRICEY is too dear for ₹10,000
    w = plan["watchlist"][0]
    high = 200.0 + len(SESSIONS) - 1
    assert w["trigger"] == pytest.approx(high * 1.001, abs=0.01) and w["stop"] == pytest.approx(w["entry"] * 0.988, abs=0.01)
    assert w["target"] == pytest.approx(w["entry"] + 2 * (w["entry"] - w["stop"]), abs=0.02)
    assert w["risk"] <= 100 and w["qty"] * w["entry"] <= 10000  # 1% risk, no borrowed money
    assert {s["key"] for s in plan["setups"]} == {"orb", "gap_and_go", "prev_high_breakout"} and not any(s["allowed"] for s in plan["setups"])
    assert any("3:00 PM" in r for r in plan["rules"]) and any("₹100" in r for r in plan["rules"])
    json.dumps(plan)  # plain numbers only: it is stored as JSON


def test_plan_allows_practice_above_the_average_and_waits_for_fresh_prices():
    with SessionLocal() as db:
        _seed_market(db, nifty_last=105.0)
        assert intraday_practice.build_plan(db, date(2026, 10, 5))["verdict"] == "practice"
        assert intraday_practice.build_plan(db, date(2026, 10, 6)) is None  # needs Monday's prices first


def _bars(day: date, prices: list[float]) -> list[IntradayBar]:
    """25 fifteen-minute bars; `prices` gives each bar's close (open = previous close)."""
    out, prev = [], prices[0]
    for i, p in enumerate(prices):
        t = datetime(day.year, day.month, day.day, 9, 15) + timedelta(minutes=15 * i)
        out.append(IntradayBar(t, prev, max(prev, p) + 0.05, min(prev, p) - 0.05, p, 1000))
        prev = p
    return out


def test_scoreboard_replays_the_day_and_scores_the_watchlist(monkeypatch):
    last, before = SESSIONS[-1], SESSIONS[-2]
    with SessionLocal() as db:
        _seed_market(db, nifty_last=95.0)
        h = 200.0 + len(SESSIONS) - 2  # STRONG's high the day before
        climb = [h - 2.0 + 1.95 * i / 24 for i in range(25)]  # the day before: a steady climb that closes at its high
        # on the last day STRONG dips, then breaks yesterday's high at 10:15 and runs to the target
        rally = [h - 1.5] * 3 + [h - 0.2] + [h + 1.0 + 0.6 * i for i in range(21)]
        frame = intraday_data._frame(_bars(before, climb) + _bars(last, rally))
        intraday_data._save("STRONG", frame)
        plan = {"watchlist": [{"symbol": "STRONG", "trigger": round(h * 1.001, 2)}, {"symbol": "WEAK", "trigger": 1.0}]}
        recap = intraday_practice.build_recap(db, last, plan)
    assert recap["date"] == last.isoformat() and recap["stocks"] == 1 and recap["filter_ok"] is False
    by = {s["key"]: s for s in recap["setups"]}
    assert by["prev_high_breakout"]["signals"] == 1 and by["prev_high_breakout"]["won"] == 1 and by["prev_high_breakout"]["target"] == 1
    first = recap["first_trades"][0]
    assert first["symbol"] == "STRONG" and first["entry_time"] == "10:15" and first["exit_reason"] == "target" and first["net_pnl"] > 0
    strong, weak = recap["watchlist"]
    assert strong["outcome"]["exit_reason"] == "target" and weak["outcome"] is None  # WEAK never triggered
    json.dumps(recap)


def test_after_close_stores_plan_and_scoreboard(monkeypatch):
    with SessionLocal() as db:
        _seed_market(db, nifty_last=95.0)
        msg = intraday_practice.after_close(db)
        assert "Plan for Mon 05 Oct: stand aside" in msg and "not ready" in msg  # no 15-minute bars in this test
        plans, recaps = intraday_practice.stored(db)
        assert list(plans) == ["2026-10-05"] and recaps == {}
        assert intraday_practice.plan_missing(db) is False


def test_three_day_row_skips_the_holiday_and_the_weekend(monkeypatch, signed_in):
    _at(monkeypatch, datetime(2026, 10, 3, 12, 0))  # Saturday
    with SessionLocal() as db:
        _seed_market(db, nifty_last=95.0)
        intraday_practice.after_close(db)
    days = signed_in.get("/api/dashboard").json()["days"]
    prev, today, nxt = days["previous"], days["today"], days["next"]
    assert prev["date"] == "2026-10-01" and prev["is_yesterday"] is False
    assert prev["skipped"] == [{"date": "2026-10-02", "reason": "Mahatma Gandhi Jayanti"}]
    assert prev["market"]["nifty"]["change_pct"] == pytest.approx(-0.05) and prev["market"]["advancers"] == 2 and prev["market"]["decliners"] == 1
    assert prev["market"]["gainers"][0]["symbol"] == "STRONG" and prev["market"]["losers"][0]["symbol"] == "WEAK"
    assert today["date"] == "2026-10-03" and today["status"] == "weekend" and today["plan"] is None and today["market"]["next_open"] == "2026-10-05"
    assert nxt["date"] == "2026-10-05" and nxt["is_tomorrow"] is False and nxt["skipped"] == [{"date": "2026-10-04", "reason": "Weekend"}]
    assert nxt["plan"]["verdict"] == "stand_aside" and nxt["waiting_for_close"] is False


def test_on_a_trading_day_tomorrows_plan_waits_for_the_close(monkeypatch):
    _at(monkeypatch, datetime(2026, 10, 5, 11, 0))  # Monday, market open
    with SessionLocal() as db:
        _seed_market(db, nifty_last=95.0)
        intraday_practice.after_close(db)
        days = day_strip.build(db)
    assert days["previous"]["date"] == "2026-10-01" and [s["date"] for s in days["previous"]["skipped"]] == ["2026-10-02", "2026-10-03", "2026-10-04"]
    assert days["today"]["status"] == "trading" and days["today"]["market"]["state"] == "open" and days["today"]["plan"]["session"] == "2026-10-05"
    assert days["next"]["date"] == "2026-10-06" and days["next"]["is_tomorrow"] and days["next"]["plan"] is None and days["next"]["waiting_for_close"] is True


# ------------------------------------------------------------------ the Refresh button
def test_prices_are_behind_only_when_a_finished_session_is_missing(monkeypatch):
    with SessionLocal() as db:
        _at(monkeypatch, datetime(2026, 10, 3, 12, 0))
        assert stock_data.prices_behind(db) is True  # nothing stored yet
        _seed_market(db, nifty_last=95.0)
        assert stock_data.prices_behind(db) is False  # Thursday is in; Friday was a holiday
        _at(monkeypatch, datetime(2026, 10, 5, 11, 0))
        assert stock_data.prices_behind(db) is False  # Monday's session isn't over
        _at(monkeypatch, datetime(2026, 10, 5, 15, 45))
        assert stock_data.prices_behind(db) is True


def test_refresh_starts_only_what_is_needed(monkeypatch, signed_in):
    started = []
    monkeypatch.setattr(scheduler, "run_job_async", lambda name, trigger="manual": started.append(name) or True)
    _at(monkeypatch, datetime(2026, 10, 3, 12, 0))
    with SessionLocal() as db:
        _seed_market(db, nifty_last=95.0)
        db.add(JobRun(job_name="amfi_nav_daily", status="ok"))
        db.commit()
    r = signed_in.post("/api/data/refresh", headers=CSRF)
    assert r.status_code == 202
    body = r.json()
    assert body["started"] == ["intraday_practice"] and started == ["intraday_practice"]  # prices are current; only the plan was missing
    assert body["prices"] == {"latest_session": "2026-10-01", "expected_session": "2026-10-01", "behind": False, "updated_at": None, "error": None}

    started.clear()
    _at(monkeypatch, datetime(2026, 10, 5, 16, 0))  # Monday after the close: a new session to fetch
    assert signed_in.post("/api/data/refresh", headers=CSRF).json()["started"] == ["stock_prices_daily"]
    fresh = signed_in.get("/api/data/freshness").json()
    assert fresh["prices"]["behind"] is True and fresh["prices"]["expected_session"] == "2026-10-05" and fresh["running"] == []
    assert signed_in.get("/api/data/freshness").status_code == 200 and signed_in.post("/api/data/refresh").status_code == 403  # writes need the CSRF header


def test_start_up_fetches_a_missed_session_or_just_the_missing_plan(monkeypatch):
    ran = []
    monkeypatch.setattr(scheduler, "run_job", lambda name, trigger="manual": ran.append(name) or True)
    monkeypatch.setattr(scheduler.intraday_data, "missing_intraday", lambda db: 0)
    _at(monkeypatch, datetime(2026, 10, 3, 12, 0))
    with SessionLocal() as db:
        _seed_market(db, nifty_last=95.0)
        for name in ("amfi_scheme_master", "amfi_nav_daily", "db_backup", "groww_instruments", "amfi_ter", "mf_scoring", "stock_backtests", "intraday_backtests"):
            db.add(JobRun(job_name=name, status="ok"))
        for inst in db.query(Instrument).all():
            inst.history_complete = True
        db.commit()
    scheduler.catch_up()
    assert ran == ["intraday_practice"]  # prices are current (Thursday); only Monday's plan is missing
    ran.clear()
    _at(monkeypatch, datetime(2026, 10, 6, 9, 0))  # Tuesday morning: Monday's session was never downloaded
    scheduler.catch_up()
    assert ran == ["stock_prices_daily"]
