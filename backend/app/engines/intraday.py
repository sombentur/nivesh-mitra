"""Intraday setups on 15-minute bars: signals and trade simulation (pure functions — no database).

Conservative assumptions throughout, so a setup has to be genuinely good to pass:
- entries are buy-stop orders filled at the trigger (or the bar's open if it jumps past it), plus slippage;
- if the entry bar also reaches the stop, the trade is counted as stopped out;
- if a later bar touches both stop and target, the stop is assumed to come first;
- a price that opens past the target is only credited with the target; one that opens past the stop takes the open;
- anything still open is sold at 3:00 PM (the close of the 2:45 bar).
"""

import math
from dataclasses import dataclass
from datetime import date, time

import numpy as np

from app.engines.backtest import position_size
from app.engines.costs import intraday_round_trip


@dataclass
class DayContext:
    """What is known before the session opens (prices in the same, unadjusted terms as that day's 15-minute bars)."""

    day: date
    prev_close: float
    prev_high: float
    prev_low: float
    trend_ok: bool  # yesterday's close above its 20-day average
    market_ok: bool  # Nifty 50 closed above its 50-day average yesterday
    avg_first_volume: float | None  # average first-bar volume over the previous 20 sessions


@dataclass
class DayBars:
    times: list[time]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray


@dataclass
class Entry:
    bar: int
    price: float
    stop: float
    target: float


@dataclass
class IntradayTrade:
    symbol: str
    setup: str
    day: date
    entry_time: str
    entry: float
    stop: float
    target: float
    qty: int
    exit_time: str
    exit: float
    exit_reason: str  # stop | target | time
    charges: float
    net_pnl: float
    r_multiple: float
    r_before_charges: float


def _t(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _risk_ok(price: float, stop: float, rules: dict) -> bool:
    if stop <= 0 or price <= stop:
        return False
    risk = (price - stop) / price
    return rules["min_risk_pct"] <= risk <= rules["max_risk_pct"]


def _breakout(bars: DayBars, trigger: float, first: int, last_entry: time, slip: float) -> tuple[int, float] | None:
    for i in range(first, len(bars.times)):
        if bars.times[i] > last_entry:
            return None
        if bars.high[i] >= trigger:
            return i, max(trigger, bars.open[i]) * (1 + slip)
    return None


def find_entry(setup: str, ctx: DayContext, bars: DayBars, rules: dict, slip: float) -> Entry | None:
    s = rules["setups"][setup]
    if not ctx.market_ok or len(bars.times) < 5 or bars.open[0] < rules["min_price"]:
        return None
    if setup == "orb":
        n = s["range_bars"]
        if not ctx.trend_ok:
            return None
        hi, lo = float(bars.high[:n].max()), float(bars.low[:n].min())
        if not s["min_range_pct"] <= (hi - lo) / hi <= s["max_range_pct"]:
            return None
        hit = _breakout(bars, hi * (1 + s["trigger_buffer"]), n, _t(s["last_entry"]), slip)
        if not hit:
            return None
        i, price = hit
        stop = lo
    elif setup == "gap_and_go":
        gap = bars.open[0] / ctx.prev_close - 1
        rng = bars.high[0] - bars.low[0]
        if not s["min_gap"] <= gap <= s["max_gap"] or rng <= 0 or ctx.avg_first_volume is None:
            return None
        if (bars.close[0] - bars.low[0]) / rng < s["first_bar_close_in_top"] or bars.volume[0] < s["first_bar_volume_multiple"] * ctx.avg_first_volume:
            return None
        hit = _breakout(bars, bars.high[0] * (1 + s["trigger_buffer"]), 1, _t(s["last_entry"]), slip)
        if not hit:
            return None
        i, price = hit
        stop = float(bars.low[0])
    elif setup == "prev_high_breakout":
        span = ctx.prev_high - ctx.prev_low
        if not ctx.trend_ok or span <= 0 or (ctx.prev_close - ctx.prev_low) / span < s["prev_close_in_top"]:
            return None
        trigger = ctx.prev_high * (1 + s["trigger_buffer"])
        if bars.open[0] >= trigger:
            return None  # opened above it: no clean breakout to buy
        first = next((k for k, t in enumerate(bars.times) if t >= _t(s["first_entry"])), len(bars.times))
        hit = _breakout(bars, trigger, first, _t(s["last_entry"]), slip)
        if not hit:
            return None
        i, price = hit
        stop = max(price * (1 - s["stop_pct"]), float(bars.low[:i].min()) if i else 0.0)
    else:
        raise ValueError(setup)
    if not _risk_ok(price, stop, rules):
        return None
    return Entry(i, round(price, 2), round(stop, 2), round(price + s["target_r"] * (price - stop), 2))


def play_out(e: Entry, bars: DayBars, rules: dict, slip: float) -> tuple[int, float, str]:
    """(exit bar, exit price, reason) under the conservative rules in the module docstring."""
    exit_at = _t(rules["exit_time"])
    if bars.low[e.bar] <= e.stop:
        return e.bar, e.stop * (1 - slip), "stop"
    last = e.bar
    for j in range(e.bar + 1, len(bars.times)):
        if bars.times[j] >= exit_at:  # the 14:45 bar (ending 15:00) is the last one held
            break
        last = j
        if bars.low[j] <= e.stop:
            return j, min(e.stop, float(bars.open[j])) * (1 - slip), "stop"
        if bars.high[j] >= e.target:
            return j, e.target * (1 - slip), "target"
    return last, float(bars.close[last]) * (1 - slip), "time"


def simulate(symbol: str, setup: str, ctx: DayContext, bars: DayBars, rules: dict, costs: dict, capital: float) -> IntradayTrade | None:
    slip = costs["intraday"]["slippage_rate"]
    e = find_entry(setup, ctx, bars, rules, slip)
    if e is None:
        return None
    qty = position_size(e.price, e.stop, capital, rules["risk_per_trade"], rules["max_position_share"])
    if qty < 1:
        return None
    j, exit_price, reason = play_out(e, bars, rules, slip)
    exit_price = round(exit_price, 2)
    charges = intraday_round_trip(e.price * qty, exit_price * qty, costs)
    gross = (exit_price - e.price) * qty
    risk = (e.price - e.stop) * qty
    return IntradayTrade(
        symbol, setup, ctx.day, bars.times[e.bar].strftime("%H:%M"), e.price, e.stop, e.target, qty,
        bars.times[j].strftime("%H:%M"), exit_price, reason, charges, round(gross - charges, 2),
        round((gross - charges) / risk, 3), round(gross / risk, 3),
    )


def summarise(trades: list[IntradayTrade], max_per_day: int) -> dict:
    if not trades:
        return {"trades": 0}
    n = len(trades)
    wins = [t for t in trades if t.net_pnl > 0]
    by_day: dict[date, list[IntradayTrade]] = {}
    for t in sorted(trades, key=lambda t: (t.day, t.entry_time, t.symbol)):
        by_day.setdefault(t.day, []).append(t)
    taken = [t for day in by_day.values() for t in day[:max_per_day]]
    return {
        "trades": n,
        "win_rate": round(len(wins) / n, 3),
        "avg_r": round(sum(t.r_multiple for t in trades) / n, 3),
        "avg_r_before_charges": round(sum(t.r_before_charges for t in trades) / n, 3),
        "avg_charges": round(sum(t.charges for t in trades) / n, 2),
        "exits": {k: sum(1 for t in trades if t.exit_reason == k) for k in ("target", "stop", "time")},
        "days_with_a_trade": len(by_day),
        "portfolio_pnl": round(sum(t.net_pnl for t in taken), 2),  # at most `max_per_day` trades a day, first come first served
        "portfolio_trades": len(taken),
        "period": [min(t.day for t in trades).isoformat(), max(t.day for t in trades).isoformat()],
    }


def verdict(build: dict, test: dict, rules: dict) -> tuple[bool, str]:
    v = rules["verdict"]
    if test.get("trades", 0) < v["min_test_trades"]:
        return False, f"Only {test.get('trades', 0)} trades in the test period (2024 on) — at least {v['min_test_trades']} needed"
    if test["avg_r"] < v["min_test_avg_r"]:
        return False, f"Lost money after charges in the test period (average {test['avg_r']:+.2f}R per trade over {test['trades']} trades)"
    if v["build_must_not_lose"] and build.get("trades", 0) and build["avg_r"] < 0:
        return False, f"Made money from 2024 on but lost in 2020–23 ({build['avg_r']:+.2f}R): not consistent enough to trust"
    return True, f"Made {test['avg_r']:+.2f}R per trade after charges from 2024 on ({test['trades']} trades), and didn't lose in 2020–23"


def nan_to_none(x: float) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x
