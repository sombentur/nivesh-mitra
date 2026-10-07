from datetime import date, datetime, time, timedelta

import numpy as np
import pytest

from app.engines import intraday as eng
from app.engines.costs import intraday_round_trip
from app.rules import load_rules

R = load_rules("intraday")
C = load_rules("costs")
SLIP = C["intraday"]["slippage_rate"]


def bars(rows):
    """rows: (open, high, low, close[, volume]) for consecutive 15-minute bars from 9:15."""
    t0 = datetime(2024, 3, 4, 9, 15)
    times = [(t0 + timedelta(minutes=15 * i)).time() for i in range(len(rows))]
    arr = np.array([r[:4] for r in rows], dtype=float)
    vol = np.array([r[4] if len(r) > 4 else 1000 for r in rows], dtype=float)
    return eng.DayBars(times, arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3], vol)


CTX = eng.DayContext(day=date(2024, 3, 4), prev_close=500.0, prev_high=505.0, prev_low=490.0, trend_ok=True, market_ok=True, avg_first_volume=1000.0)
FLAT = (501, 501.5, 500.5, 501)


def test_intraday_charges_are_lower_than_delivery():
    assert intraday_round_trip(10000, 10000, C) == pytest.approx(27.15, abs=0.05)  # ₹10 + ₹10 brokerage, STT on the sell only…


def test_orb_breakout_hits_target():
    day = bars([(500, 504, 499, 503), (503, 504, 500, 502), (502, 505, 501, 504.5), (504.5, 512, 504, 511), (511, 520, 510, 518)] + [FLAT] * 20)
    e = eng.find_entry("orb", CTX, day, R, SLIP)
    assert e.bar == 2 and e.price == pytest.approx(504 * 1.0005 * (1 + SLIP), abs=0.01) and e.stop == 499
    t = eng.simulate("X", "orb", CTX, day, R, C, 10000)
    assert t.exit_reason == "target" and t.exit == pytest.approx(round(e.target * (1 - SLIP), 2))
    assert t.r_multiple < t.r_before_charges  # charges always cost something


def test_stop_in_the_entry_bar_counts_as_a_loss():
    day = bars([(500, 504, 499, 503), (503, 504, 500, 502), (502, 505, 498, 499)] + [FLAT] * 22)
    t = eng.simulate("X", "orb", CTX, day, R, C, 10000)
    assert t.exit_reason == "stop" and t.exit_time == "09:45" and t.r_multiple < -1


def test_bar_touching_stop_and_target_is_a_stop():
    day = bars([(500, 504, 499, 503), (503, 504, 500, 502), (502, 505, 501, 504.5), (504.5, 530, 490, 505)] + [FLAT] * 21)
    assert eng.simulate("X", "orb", CTX, day, R, C, 10000).exit_reason == "stop"


def test_time_exit_at_three_pm():
    day = bars([(500, 504, 499, 503), (503, 504, 500, 502), (502, 505, 501, 504.5)] + [(505, 506, 504, 505.5)] * 22)
    t = eng.simulate("X", "orb", CTX, day, R, C, 10000)
    assert t.exit_reason == "time" and t.exit_time == "14:45"  # the 14:45 bar closes at 3:00 PM


def test_filters_block_trades():
    day = bars([(500, 504, 499, 503), (503, 504, 500, 502), (502, 505, 501, 504.5)] + [FLAT] * 22)
    assert eng.find_entry("orb", eng.DayContext(**{**CTX.__dict__, "market_ok": False}), day, R, SLIP) is None  # Nifty below its 50-day average
    assert eng.find_entry("orb", eng.DayContext(**{**CTX.__dict__, "trend_ok": False}), day, R, SLIP) is None
    wide = bars([(500, 530, 495, 503), (503, 504, 500, 502), (502, 531, 501, 504.5)] + [FLAT] * 22)
    assert eng.find_entry("orb", CTX, wide, R, SLIP) is None  # opening range over 2.5% wide


def test_gap_and_go_needs_volume_and_a_strong_first_bar():
    strong = bars([(510, 514, 509, 513.5, 3000), (513.5, 516, 513, 515)] + [(515, 516, 514, 515.5)] * 23)
    e = eng.find_entry("gap_and_go", CTX, strong, R, SLIP)
    assert e and e.bar == 1 and e.stop == 509
    quiet = bars([(510, 514, 509, 513.5, 1500), (513.5, 516, 513, 515)] + [(515, 516, 514, 515.5)] * 23)
    assert eng.find_entry("gap_and_go", CTX, quiet, R, SLIP) is None


def test_prev_high_breakout_skips_gap_over_the_trigger():
    ctx = eng.DayContext(**{**CTX.__dict__, "prev_close": 504.0})  # closed near yesterday's high of 505
    above = bars([(507, 508, 506, 507)] + [FLAT] * 24)
    assert eng.find_entry("prev_high_breakout", ctx, above, R, SLIP) is None
    later = bars([(503, 504, 502, 503), (503, 506, 502.5, 505.8)] + [FLAT] * 23)
    e = eng.find_entry("prev_high_breakout", ctx, later, R, SLIP)
    assert e and e.bar == 1 and e.stop >= e.price * (1 - 0.012) - 0.01


def test_verdict_uses_the_test_period():
    build, test = {"trades": 500, "avg_r": 0.1}, {"trades": 300, "avg_r": 0.08}
    assert eng.verdict(build, test, R)[0] is True
    assert eng.verdict(build, {"trades": 50, "avg_r": 0.5}, R)[0] is False
    assert eng.verdict({"trades": 500, "avg_r": -0.2}, test, R)[0] is False  # inconsistent across periods
    assert "Lost money" in eng.verdict(build, {"trades": 300, "avg_r": -0.1}, R)[1]


def test_exit_time_rule_is_three_pm():
    assert R["exit_time"] == "15:00" and time(15, 0) > time(14, 45)


def test_contexts_take_yesterday_from_the_bars_and_skip_ex_dates():
    """The 15-minute bars aren't split-adjusted, so yesterday's levels must come from the bars, not the daily candles."""
    import pandas as pd

    from app.services.intraday_data import _frame
    from app.services.intraday_trading import _contexts
    from tests.test_intraday_data import _session_bars

    days = [d.date() for d in pd.bdate_range("2026-09-21", periods=5)]
    # three sessions near ₹1,000, then a 1:1 bonus: the last two sessions trade near ₹500
    raw = [b for d, px in zip(days, (1000.0, 1010.0, 1020.0, 510.0, 515.0)) for b in _session_bars(d, open_=px, drift=0.1)]
    # the daily candles (from Groww's adjusted feed) show no jump at all
    daily = pd.DataFrame({"close": [500.0, 505.0, 510.0, 511.0, 516.0]}, index=pd.DatetimeIndex(days))
    ctx = _contexts(daily, _frame(raw), {d: True for d in days}, trend_sma=2)
    assert sorted(ctx) == [days[1], days[2], days[4]]  # no "yesterday" for the first session; the ex-date (4th) is skipped
    assert ctx[days[1]].prev_close == pytest.approx(1002.5) and ctx[days[1]].prev_high == pytest.approx(1002.4 * 1.004)
    assert ctx[days[4]].prev_close == pytest.approx(512.5)  # same price basis as that day's bars
    assert ctx[days[2]].trend_ok is True and ctx[days[1]].trend_ok is False  # 2-day average needs two closes
    assert ctx[days[4]].avg_first_volume is None  # volumes around a split aren't comparable
