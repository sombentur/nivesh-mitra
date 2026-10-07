import shutil
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.connectors import groww
from app.connectors.groww import Candle, IntradayBar, parse_candle, parse_intraday, per_bar_volume, split_symbol
from app.connectors.http import SourceUnavailable
from app.db.base import SessionLocal
from app.db.models import Instrument, PriceDaily
from app.engines.adjust import detect
from app.services import groww_service, intraday_data, stock_data
from app.services.stock_data import load_bars, store_candles

IST = stock_data.IST


@pytest.fixture(autouse=True)
def empty_intraday_folder():
    shutil.rmtree(intraday_data.folder(), ignore_errors=True)
    yield


def _at(monkeypatch, when: datetime):
    """Freeze 'now' (exchange time) for the price services."""
    now = when.replace(tzinfo=IST)
    monkeypatch.setattr(stock_data, "now_ist", lambda: now)
    monkeypatch.setattr(intraday_data, "now_ist", lambda: now)


def _bars(closes, opens=None, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    c = np.array(closes, dtype=float)
    o = np.array(opens if opens is not None else c, dtype=float)
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.01, "low": np.minimum(o, c) * 0.99, "close": c, "volume": 1000}, index=idx)


# ------------------------------------------------------------------ split / bonus detection on unadjusted sessions
def test_bonus_and_split_are_detected():
    b = _bars([1000.0] * 5 + [505.0] * 5 + [50.0] * 5)  # 1:1 bonus, then a 1:10 split
    assert [f for _, f in detect(b)] == [2.0, 10.0]


def test_ordinary_bad_days_and_real_crashes_are_not_events():
    assert detect(_bars([1000.0] * 5 + [760.0] * 5)) == []  # a 24% fall
    # a real 36% crash that opened only 7% lower (PB Fintech, 24-Sep-2026): the open says it is not a split
    assert detect(_bars([1886.0] * 5 + [1207.0] * 5, opens=[1886.0] * 5 + [1750.0] + [1207.0] * 4)) == []


def test_open_is_preferred_over_close_on_the_ex_date():
    # ex-date opens at exactly half (1:1 bonus) and then rallies 20% — the close alone would look like a 1:2 bonus
    b = _bars([1000.0] * 5 + [600.0] * 5, opens=[1000.0] * 5 + [500.0] + [600.0] * 4)
    assert [f for _, f in detect(b)] == [2.0]


# ------------------------------------------------------------------ parsing the two feeds
def test_parse_intraday_keeps_the_regular_session_only():
    assert parse_intraday(["2021-06-01T09:15:00", 10, 11, 9, 10.5, 100, None]).ts == datetime(2021, 6, 1, 9, 15)
    assert parse_intraday(["2021-06-01T15:15:00", 10, 11, 9, 10.5, 100, None]) is not None
    assert parse_intraday(["2021-06-01T15:30:00", 10, 10, 10, 10, 5, None]) is None  # closing tick
    assert parse_intraday(["bad", 1, 1, 1, 1, 1]) is None


def test_epoch_timestamps_are_read_in_exchange_time():
    # 1790826300 = 1 Oct 2026 09:15 IST; 1790793000 = 1 Oct 2026 00:00 IST (a daily candle)
    assert parse_intraday([1790826300, 1180.1, 1181.9, 1177.9, 1181.2, 1474730]).ts == datetime(2026, 10, 1, 9, 15)
    c = parse_candle([1790793000, 1180.1, 1183.9, 1160.8, 1167.7, 16771221])
    assert c.day == date(2026, 10, 1) and c.open == 1180.1 and c.volume == 16771221
    assert parse_candle([1790793000, None, 22600.0, 22400.0, 22421.95, None]).open is None  # an index: no open, no volume


def test_running_total_volume_becomes_per_bar_volume():
    def bar(d, i, vol):
        return IntradayBar(datetime(2026, 10, d, 9, 15) + timedelta(minutes=15 * i), 10, 11, 9, 10, vol)

    day1 = [bar(1, i, v) for i, v in enumerate([1000, 1600, 1600, 2500])]  # running total
    day2 = [bar(5, i, v) for i, v in enumerate([900, 400, 700])]  # already per bar (not a running total)
    out = per_bar_volume(day1 + day2)
    assert [b.volume for b in out] == [1000, 600, 0, 900, 900, 400, 700]


def test_groww_symbol_is_split_into_exchange_and_symbol():
    assert split_symbol("NSE-BAJAJ-AUTO") == ("NSE", "BAJAJ-AUTO")
    assert split_symbol("BSE-SENSEX") == ("BSE", "SENSEX") and split_symbol("NSE-M&M") == ("NSE", "M&M")


def test_daily_candles_use_the_current_feed(monkeypatch):
    asked = []

    class Sdk:
        def get_historical_candle_data(self, **kw):
            asked.append(kw)
            return {"candles": [[1790793000, 1180.1, 1183.9, 1160.8, 1167.7, 16771221]]}

    client = groww.GrowwReadOnlyClient("token", "JBSWY3DPEHPK3PXP")
    monkeypatch.setattr(client, "_sdk", lambda: Sdk())
    out = client.daily_candles("BSE-RELIANCE", date(2020, 1, 1), date(2026, 10, 3))
    assert [c.day for c in out] == [date(2026, 10, 1)]
    assert len(asked) == 3 and all(a["exchange"] == "BSE" and a["trading_symbol"] == "RELIANCE" and a["interval_in_minutes"] == 1440 for a in asked)
    assert asked[0]["start_time"] == "2020-01-01 00:00:00" and asked[-1]["end_time"] == "2026-10-03 23:59:59"  # ≤ 1,080 days each


# ------------------------------------------------------------------ 15-minute store
def _session_bars(day: date, open_: float = 100.0, drift: float = 0.1, n: int = 25) -> list[IntradayBar]:
    out, price = [], open_
    for i in range(n):
        t = datetime(day.year, day.month, day.day, 9, 15) + timedelta(minutes=15 * i)
        out.append(IntradayBar(t, price, price * 1.004, price * 0.996, price + drift, 1000))
        price += drift
    return out


def test_merge_keeps_whichever_answer_covers_more_of_the_day():
    frame = intraday_data._frame
    stored = frame(_session_bars(date(2026, 9, 28)) + _session_bars(date(2026, 9, 29), n=19))
    newer = frame(_session_bars(date(2026, 9, 28), n=10) + _session_bars(date(2026, 9, 29), open_=200.0) + _session_bars(date(2026, 9, 30)))
    merged = intraday_data.merge_days(stored, newer)
    counts = merged.groupby(merged.index.normalize()).size()
    assert list(counts) == [25, 25, 25]
    assert merged.loc["2026-09-28 09:15", "open"] == 100.0  # the shorter new answer didn't replace a full day
    assert merged.loc["2026-09-29 09:15", "open"] == 200.0  # the complete new day replaced the cut-short one


def test_tail_starts_at_the_first_incomplete_recent_session():
    frame = intraday_data._frame
    today = date(2026, 10, 3)
    full = frame([b for d in pd.bdate_range("2026-09-21", "2026-10-01") for b in _session_bars(d.date())])
    assert intraday_data.tail_start(full, today) == date(2026, 10, 1)  # nothing short: just re-read the last day
    holed = intraday_data.merge_days(full[full.index.normalize() != pd.Timestamp("2026-09-29")], frame(_session_bars(date(2026, 9, 29), n=19)))
    assert intraday_data.tail_start(holed, today) == date(2026, 9, 29)
    assert intraday_data.tail_start(full, today, heal=True) == today - timedelta(days=intraday_data.HEAL_WINDOW_DAYS)
    assert intraday_data.tail_start(intraday_data._empty(), today) == today - timedelta(days=intraday_data.RECENT_FEED_DAYS)


class FakeFeeds:
    """The backtesting feed runs two sessions behind and its newest session is cut short; the candle-data feed is complete."""

    def __init__(self):
        self.calls = []

    def intraday_candles(self, symbol, start, end):
        self.calls.append(("deep", start, end))
        days = [d.date() for d in pd.bdate_range(start, end)][:-2]
        return [b for d in days for b in _session_bars(d)][:-6]

    def recent_intraday_candles(self, symbol, start, end):
        self.calls.append(("recent", start, end))
        return [b for d in pd.bdate_range(start, end) for b in _session_bars(d.date(), open_=101.0)]


@pytest.fixture
def universe_stock():
    with SessionLocal() as db:
        inst = Instrument(symbol="TESTCO", groww_symbol="NSE-TESTCO", in_universe=True, universe_rank=1)
        db.add(inst)
        db.flush()
        db.add(PriceDaily(instrument_id=inst.id, date=date(2026, 9, 29), open=110.0, high=110.0, low=99.0, close=102.5, volume=25000))
        db.commit()
    yield


def test_sync_combines_both_feeds_and_then_only_rereads_the_last_day(universe_stock, monkeypatch):
    fake = FakeFeeds()
    monkeypatch.setattr(groww_service, "client", lambda db: fake)
    monkeypatch.setattr(intraday_data, "rules", lambda: {"universe": {"history_start": "2026-09-21"}})
    _at(monkeypatch, datetime(2026, 9, 30, 18, 0))
    with SessionLocal() as db:
        assert intraday_data.missing_intraday(db) == 1
        assert "updated for 1 of 1 stocks (0 failed)" in intraday_data.sync_intraday(db)
        assert intraday_data.missing_intraday(db) == 0
        bars = intraday_data.load("TESTCO")
        counts = bars.groupby(bars.index.normalize()).size()
        assert len(counts) == 8 and set(counts) == {25}  # 21–30 Sep, every session complete
        assert bars.index[0] == pd.Timestamp("2026-09-21 09:15") and bars.index[-1] == pd.Timestamp("2026-09-30 15:15")
        assert [c[0] for c in fake.calls] == ["deep", "recent"] and fake.calls[1][1] == date(2026, 9, 21)  # first run re-reads recent weeks
        assert db.query(PriceDaily).one().open == 110.0  # daily candles are never touched from here

        assert "updated for 0 of 1" in intraday_data.sync_intraday(db)  # nothing new
        assert fake.calls[-1] == ("recent", date(2026, 9, 30), date(2026, 9, 30)) and len(fake.calls) == 3

        _at(monkeypatch, datetime(2026, 10, 1, 18, 0))
        assert "updated for 1 of 1" in intraday_data.sync_intraday(db)
        assert fake.calls[-1] == ("recent", date(2026, 9, 30), date(2026, 10, 1))
        assert len(intraday_data.load("TESTCO")) == 9 * 25


def test_session_summary_comes_from_the_bars_themselves():
    df = intraday_data._frame(_session_bars(date(2026, 9, 29)) + _session_bars(date(2026, 9, 30), open_=50.0))
    s = intraday_data.daily_from_intraday(df)
    assert list(s["bars"]) == [25, 25] and s["open"].iloc[1] == 50.0 and s["first_volume"].iloc[0] == 1000 and s["volume"].iloc[0] == 25000
    assert s["close"].iloc[0] == pytest.approx(102.5)
    assert [f for _, f in detect(s)] == [2.0]  # the halving between the two sessions reads as a 1:1 bonus


# ------------------------------------------------------------------ daily candles in the database
def test_newer_candles_replace_older_ones_but_keep_known_opens(universe_stock):
    with SessionLocal() as db:
        inst = db.query(Instrument).one()
        store_candles(db, inst, [Candle(date(2026, 9, 29), None, 104.0, 99.5, 101.0, 30000)])
        db.commit()
        db.expire_all()  # read what's in the database, not the session's copy
        row = db.query(PriceDaily).one()
        assert (row.open, row.high, row.low, row.close, row.volume) == (110.0, 104.0, 99.5, 101.0, 30000)
        assert load_bars(db, inst.id)["close"].iloc[0] == 101.0  # returned as stored (already adjusted by Groww)


def test_todays_candle_is_not_stored_before_the_close(universe_stock, monkeypatch):
    today = [Candle(date(2026, 9, 30), 101.0, 103.0, 100.0, 102.0, 5000)]
    with SessionLocal() as db:
        inst = db.query(Instrument).one()
        _at(monkeypatch, datetime(2026, 9, 30, 11, 0))
        store_candles(db, inst, today)
        db.commit()
        assert db.query(PriceDaily).count() == 1 and inst.history_end is None
        _at(monkeypatch, datetime(2026, 9, 30, 15, 45))
        store_candles(db, inst, today)
        db.commit()
        assert db.query(PriceDaily).count() == 2 and inst.history_end == date(2026, 9, 30)


class RebasingGroww:
    """After a 1:1 bonus Groww halves every past price in its answers."""

    def __init__(self):
        self.calls = []

    def daily_candles(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if not symbol.endswith("TESTCO"):
            return []
        days = [d.date() for d in pd.bdate_range(max(start, date(2026, 6, 1)), end)]
        return [Candle(d, 50.0, 52.0, 49.0, 51.0, 2000) for d in days]


def test_a_rebased_history_is_downloaded_again(monkeypatch):
    with SessionLocal() as db:
        inst = Instrument(symbol="TESTCO", groww_symbol="NSE-TESTCO", in_universe=True, universe_rank=1, history_complete=True)
        db.add(inst)
        db.flush()
        for d in pd.bdate_range("2026-06-01", "2026-09-29"):
            db.add(PriceDaily(instrument_id=inst.id, date=d.date(), open=100.0, high=104.0, low=98.0, close=102.0, volume=1000))
        db.commit()
        fake = RebasingGroww()
        monkeypatch.setattr(groww_service, "client", lambda db: fake)
        monkeypatch.setattr(stock_data, "update_bse_tape", lambda *a: 0)
        _at(monkeypatch, datetime(2026, 9, 30, 18, 0))
        stock_data.update_daily_prices(db)
        db.expire_all()
        closes = {r.close for r in db.query(PriceDaily).all()}
        assert closes == {51.0}  # every stored day is on the new basis, none left at 102
        stock_calls = [c for c in fake.calls if c[0] == "NSE-TESTCO"]
        assert stock_calls[0][1] == date(2026, 9, 20) and stock_calls[1][1] == date(2020, 1, 1)  # the 10-day update, then the full history


def test_replace_history_refuses_a_much_shorter_download(universe_stock):
    with SessionLocal() as db:
        inst = db.query(Instrument).one()
        for d in pd.bdate_range("2026-08-03", "2026-09-28"):
            db.add(PriceDaily(instrument_id=inst.id, date=d.date(), open=100.0, high=104.0, low=98.0, close=102.0, volume=1000))
        db.commit()
        with pytest.raises(SourceUnavailable, match="keeping what is stored"):
            stock_data.replace_history(db, inst, [Candle(date(2026, 9, 29), 1.0, 1.0, 1.0, 1.0, 1)])
        assert db.query(PriceDaily).count() == 42  # 41 sessions seeded here + the fixture's one: nothing was deleted
