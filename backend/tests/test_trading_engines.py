from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.engines import backtest as bt
from app.engines import costs, indicators, setups
from app.engines.setups import Signal
from app.rules import load_rules

COSTS = load_rules("costs")
RULES = load_rules("trading")
RISK = RULES["risk"]


# ---------------------------------------------------------------- costs
def test_groww_delivery_charges_for_a_small_trade():
    rt = costs.round_trip(2000, 2000, COSTS)
    assert rt["buy"]["brokerage"] == 5.0  # 0.1% would be ₹2 → minimum ₹5
    assert rt["sell"]["dp_charge"] == 20.0
    assert rt["total"] == pytest.approx(39.85, abs=0.05)  # ≈ 2% of ₹2,000
    assert costs.breakeven_move(2000, COSTS) == pytest.approx(0.0199, abs=0.0005)


def test_cost_drag_shrinks_as_capital_grows():
    small, big = costs.cost_drag(10000, COSTS, 0.01, 0.35), costs.cost_drag(100000, COSTS, 0.01, 0.35)
    assert small["qty"] == 3 and small["charges_in_r"] == pytest.approx(0.47, abs=0.01)
    assert small["breakeven_win_rate"] == pytest.approx((1 + small["charges_in_r"]) / 3, abs=0.002)
    assert big["charges_in_r"] < small["charges_in_r"] and big["breakeven_win_rate"] < small["breakeven_win_rate"]
    assert costs.cost_drag(2000, COSTS, 0.01, 0.35)["qty"] == 0  # can't afford one ₹1,000 share within 35%


def test_brokerage_cap_and_no_dp_for_tiny_sells():
    assert costs.brokerage(50000, COSTS) == 20.0
    assert costs.sell_charges(90, COSTS).dp_charge == 0.0


# ---------------------------------------------------------------- indicators
def _bars(closes, spread=0.01, volume=1000):
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c * 0.998, "high": c * (1 + spread), "low": c * (1 - spread), "close": c, "volume": volume}, index=idx)


def test_indicator_basics():
    df = _bars(np.linspace(100, 200, 300))
    ind = indicators.add_indicators(df)
    assert ind["sma20"].iloc[-1] == pytest.approx(df["close"].iloc[-20:].mean())
    assert ind["rsi14"].iloc[-1] == pytest.approx(100.0)  # only up days
    assert ind["atr14"].iloc[-1] > 0 and np.isnan(ind["sma200"].iloc[198]) and not np.isnan(ind["sma200"].iloc[199])
    flat = _bars([100.0] * 60, spread=0.02)
    assert indicators.atr(flat).iloc[-1] == pytest.approx(4.0, rel=0.01)  # high−low = ₹4 every day


def test_rsi_balanced_moves_is_fifty():
    closes = [100 + (1 if i % 2 else 0) for i in range(100)]
    assert indicators.rsi(pd.Series(closes, dtype=float)).iloc[-1] == pytest.approx(50, abs=3)


# ---------------------------------------------------------------- setups (conditions on a hand-built indicator row)
def _row(**kw):
    base = dict(open=99.0, high=101.0, low=98.5, close=100.0, volume=1000, sma20=99.0, sma50=95.0, sma200=90.0, rsi14=50.0,
                atr14=2.0, vol20_prev=1000.0, high_prev_n=110.0, low_swing=97.0, low_to_sma20_min=0.995, close_in_range=0.6, green=True)
    base.update(kw)
    return pd.DataFrame([base], index=pd.DatetimeIndex(["2026-09-29"]))


def test_trend_pullback_signal_and_levels():
    sigs = setups.trend_pullback(_row(), RULES["setups"]["trend_pullback"], 2.0)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.stop == pytest.approx(max(100 - 2 * 2, 97 - 0.2 * 2))  # 96.6
    assert (s.entry_low, s.entry_high) == (99.5, 100.5)
    assert s.target == pytest.approx(100.5 + 2 * (100.5 - 96.6))  # 2R from the top of the entry range
    assert s.reward_risk_worst == pytest.approx(2.0, abs=0.01)


@pytest.mark.parametrize("kw", [dict(close=89.0, low=88, sma20=88.5, low_swing=87), dict(rsi14=70), dict(green=False), dict(low_to_sma20_min=1.05)])
def test_trend_pullback_rejects(kw):
    assert setups.trend_pullback(_row(**kw), RULES["setups"]["trend_pullback"], 2.0) == []


def test_volume_breakout_signal():
    row = _row(close=112.0, high=112.5, low=108.0, open=108.5, volume=2000, high_prev_n=110.0, close_in_range=0.89, rsi14=65, sma50=100)
    sigs = setups.volume_breakout(row, RULES["setups"]["volume_breakout"], 2.0)
    assert len(sigs) == 1
    s = sigs[0]
    assert s.stop == pytest.approx(110 - 0.5 * 2)  # breakout level − 0.5 ATR = 109
    assert s.entry_high == pytest.approx(113.12)
    assert s.target == pytest.approx(113.12 + 2.5 * (113.12 - 109), abs=0.01)
    assert s.reward_risk_worst == pytest.approx(2.5, abs=0.01)


def test_volume_breakout_needs_volume():
    row = _row(close=112.0, high=112.5, low=108.0, volume=1200, high_prev_n=110.0, close_in_range=0.89)
    assert setups.volume_breakout(row, RULES["setups"]["volume_breakout"], 2.0) == []


# ---------------------------------------------------------------- backtest mechanics
SIG = Signal("trend_pullback", date(2026, 9, 1), 500.0, 497.5, 502.5, 480.0, 540.0, 10)


def _after(rows):
    """rows: list of (open, high, low, close) for the sessions after the signal."""
    days = pd.bdate_range("2026-09-02", periods=len(rows))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=days)
    df["volume"] = 1000
    signal_day = pd.DataFrame([[500, 505, 495, 500, 1000]], columns=df.columns, index=pd.DatetimeIndex(["2026-09-01"]))
    return pd.concat([signal_day, df])


def _sim(rows, capital=10000):
    return bt.simulate("TEST", _after(rows), SIG, capital, RISK, COSTS)


def test_position_size_rule():
    assert bt.position_size(500, 480, 10000, 0.01, 0.35) == 5  # ₹100 risk ÷ ₹20 per share
    assert bt.position_size(5000, 4900, 10000, 0.01, 0.35) == 0  # can't afford one share within 35%


def test_target_hit_is_a_win_after_costs():
    t = _sim([(501, 510, 499, 508), (508, 541, 507, 539)])
    assert t.exit_reason == "target" and t.exit == 540.0 and t.qty == 4
    assert t.net_pnl > 0 and t.charges > 0 and t.r_multiple < 2  # costs eat into the 2R


def test_stop_hit_loses_about_one_r_plus_costs():
    t = _sim([(501, 503, 495, 496), (496, 497, 479, 480)])
    assert t.exit_reason == "stop" and t.net_pnl < 0 and t.r_multiple < -1


def test_gap_up_above_entry_range_is_missed():
    assert _sim([(510, 515, 505, 512)]) is None


def test_limit_order_fills_when_price_dips_back_to_it():
    t = _sim([(510, 515, 501, 512), (512, 541, 511, 539)])  # opened above the range, dipped to ₹502.50 later
    assert t is not None and t.entry == 502.5


def _sim_nan_open(rows):
    df = _after(rows)
    df.loc[df.index[1]:, "open"] = float("nan")
    return bt.simulate("TEST", df, SIG, 10000, RISK, COSTS)


def test_missing_open_assumes_worst_limit_fill():
    t = _sim_nan_open([(None, 501, 495, 500), (None, 541, 499, 539)])
    assert t.entry == 501.0  # the day's high was below the limit: assume we paid the high
    assert t.exit_reason == "target"
    assert _sim_nan_open([(None, 505, 503, 504)]) is None  # never traded down to the limit


def test_missing_open_gap_down_sells_mid_day():
    t = _sim_nan_open([(None, 503, 495, 496), (None, 470, 460, 465)])  # whole day below the ₹480 stop
    assert t.exit_reason == "stop" and t.exit == pytest.approx(465 * (1 - COSTS["slippage_rate"]), abs=0.01)


def test_green_day_falls_back_to_previous_close_without_open():
    df = _bars([100, 101, 100.5] * 30)
    df.loc[df.index[-2:], "open"] = float("nan")
    ind = indicators.add_indicators(df)
    assert not bool(ind["green"].iloc[-1])  # 100.5 closed below yesterday's 101
    assert bool(ind["green"].iloc[-2])  # 101 closed above yesterday's 100


def test_same_day_stop_and_target_assumes_stop():
    t = _sim([(501, 545, 478, 520)])
    assert t.exit_reason == "stop"


def test_gap_down_through_stop_sells_at_open():
    t = _sim([(501, 503, 495, 496), (470, 475, 465, 472)])
    assert t.exit_reason == "stop" and t.exit == pytest.approx(470 * (1 - COSTS["slippage_rate"]), abs=0.01)


def test_time_exit_after_max_hold():
    t = _sim([(501, 505, 495, 500)] * 10)
    assert t.exit_reason == "time" and t.hold_days == 10


def test_unfinished_trade_is_ignored():
    assert _sim([(501, 505, 495, 500)] * 3) is None


def test_summary_and_verdict():
    def mk(pnl, r, d):
        return bt.Trade("X", "s", d, d, 100, 95, 110, 1, d + timedelta(days=5), 100 + pnl, "target" if pnl > 0 else "stop", 1, pnl, r, 5)

    trades = [mk(10, 1.8, date(2025, 1, 1) + timedelta(days=7 * i)) if i % 2 else mk(-6, -1.1, date(2025, 1, 1) + timedelta(days=7 * i)) for i in range(120)]
    s = bt.summarise(trades, 10000, 3)
    assert s["trades"] == 120 and s["win_rate"] == 0.5 and s["avg_r"] == pytest.approx(0.35)
    assert s["portfolio"]["final_equity"] == pytest.approx(10000 + 60 * 10 - 60 * 6)
    ok, why = bt.verdict(s, RULES)
    assert ok and "+0.35R" in why
    assert bt.verdict({"trades": 20, "avg_r": 1.0}, RULES)[0] is False
    assert bt.verdict({**s, "avg_r": -0.1}, RULES)[0] is False
    # risk ₹5 a trade, charges ₹1: adding charges back gives (10+1)/5 and (-6+1)/5
    assert s["avg_r_before_charges"] == pytest.approx((11 / 5 + -5 / 5) / 2)


def test_portfolio_replay_stops_when_the_money_is_gone():
    d0 = date(2025, 1, 1)
    losers = [bt.Trade("X", "s", d0, d0 + timedelta(days=7 * i), 100, 95, 110, 30, d0 + timedelta(days=7 * i + 5), 80, "stop", 20, -620, -4.1, 5) for i in range(30)]
    p = bt.summarise(losers, 10000, 3)["portfolio"]
    assert p["final_equity"] == 0 and p["max_drawdown"] == -1.0 and p["cagr"] == -1.0
    assert p["ruined_on"] == (d0 + timedelta(days=7 * 16 + 5)).isoformat()  # 17th loss of ₹620 takes ₹10,000 below zero
    assert p["curve"][-1][1] == 0.0 and min(v for _, v in p["curve"]) == 0.0
