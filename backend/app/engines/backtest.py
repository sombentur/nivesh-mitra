"""Backtest a setup on daily bars, the way you'd really trade it — with Groww's charges and slippage.

Deliberately conservative:
- Buy at the next day's OPEN, only if it opens inside the entry range (a gap up above it = missed trade).
- If the stop-loss and the target are both touched on the same day, assume the stop was hit first.
- A gap down through the stop sells at the (worse) opening price.
- Slippage on every market-style fill; full delivery charges on every trade (rules/costs.yaml).
- Position size from the same 1%-risk rule the app uses for real ideas, on the same capital — so small-account
  cost drag is included, and stocks too expensive for the account are skipped.
"""

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.engines.costs import round_trip
from app.engines.setups import Signal


def position_size(entry: float, stop: float, capital: float, risk_share: float, max_position_share: float) -> int:
    """R-05: lose at most `risk_share` of capital at the stop; never put more than `max_position_share` in one trade."""
    if entry <= stop or entry <= 0:
        return 0
    by_risk = math.floor(capital * risk_share / (entry - stop))
    by_cap = math.floor(capital * max_position_share / entry)
    return max(0, min(by_risk, by_cap))


@dataclass
class Trade:
    symbol: str
    setup: str
    signal_day: date
    entry_day: date
    entry: float
    stop: float
    target: float
    qty: int
    exit_day: date
    exit: float
    exit_reason: str  # stop | target | time
    charges: float
    net_pnl: float
    r_multiple: float
    hold_days: int


def _open(bar) -> float | None:
    return None if bar.open is None or pd.isna(bar.open) else float(bar.open)


def entry_fill(bar, entry_high: float, stop: float, slip: float) -> float | None:
    """A LIMIT buy at the top of the entry range (what the Groww steps tell you to place).

    Opens at or below the limit → bought at the open (+slippage). Opens above it but dips to it later → bought at
    the limit. Never trades down to it → missed. Opens at/below the stop → skipped.
    If Groww didn't provide the day's open, assume the worst fill the limit allows.
    """
    o = _open(bar)
    if o is not None:
        if o <= stop:
            return None
        if o <= entry_high:
            return round(o * (1 + slip), 2)
        return round(entry_high, 2) if bar.low <= entry_high else None
    if bar.high <= stop or bar.low > entry_high:
        return None
    return round(min(entry_high, bar.high), 2)


def exit_fill(bar, entry_day: bool, stop: float, target: float, slip: float) -> tuple[float, str] | None:
    """Did this day's bar end the trade? Stop is checked before target (the cautious assumption)."""
    o = _open(bar)
    if not entry_day:
        if o is not None and o <= stop:
            return o * (1 - slip), "stop"  # gapped down through the stop
        if o is not None and o >= target:
            return o, "target"
        if o is None and bar.high < stop:
            return (bar.high + bar.low) / 2 * (1 - slip), "stop"  # traded wholly below the stop: gapped down; assume mid-day
        if o is None and bar.low > target:
            return target, "target"
    if bar.low <= stop:
        return stop * (1 - slip), "stop"
    if bar.high >= target:
        return target, "target"
    return None


def simulate(symbol: str, bars: pd.DataFrame, sig: Signal, capital: float, risk: dict, cost_rules: dict) -> Trade | None:
    """Play out one signal on the bars after it. Returns None if the trade would not have happened."""
    after = bars[bars.index > pd.Timestamp(sig.day)]
    if after.empty:
        return None
    slip = cost_rules["slippage_rate"]
    entry = entry_fill(after.iloc[0], sig.entry_high, sig.stop, slip)
    if entry is None:
        return None
    qty = position_size(entry, sig.stop, capital, risk["risk_per_trade"], risk["max_position_share"])
    if qty < 1:
        return None
    window = after.iloc[: sig.max_hold_days]
    exit_price, reason, exit_day = None, "time", window.index[-1]
    for i, (day, bar) in enumerate(window.iterrows()):
        hit = exit_fill(bar, i == 0, sig.stop, sig.target, slip)
        if hit:
            (exit_price, reason), exit_day = hit, day
            break
    if exit_price is None:
        if len(window) < sig.max_hold_days:
            return None  # still open at the end of the data — not a finished trade
        exit_price = window.iloc[-1].close * (1 - slip)
    exit_price = round(exit_price, 2)
    charges = round_trip(entry * qty, exit_price * qty, cost_rules)["total"]
    net = round((exit_price - entry) * qty - charges, 2)
    return Trade(
        symbol, sig.setup, sig.day, after.index[0].date(), entry, sig.stop, sig.target, qty,
        pd.Timestamp(exit_day).date(), exit_price, reason, charges, net,
        round(net / ((entry - sig.stop) * qty), 3), len(bars[(bars.index >= after.index[0]) & (bars.index <= exit_day)]),
    )


def summarise(trades: list[Trade], capital: float, max_positions: int) -> dict:
    """Setup statistics plus a simple portfolio replay (at most `max_positions` open at once, first come first served)."""
    if not trades:
        return {"trades": 0}
    rs = [t.r_multiple for t in trades]
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl <= 0]
    streak = worst = 0
    for t in sorted(trades, key=lambda t: t.entry_day):
        streak = streak + 1 if t.net_pnl <= 0 else 0
        worst = max(worst, streak)

    taken: list[Trade] = []
    for t in sorted(trades, key=lambda t: (t.entry_day, t.symbol)):
        if sum(1 for o in taken if o.entry_day <= t.entry_day < o.exit_day) < max_positions:
            taken.append(t)
    equity, peak, max_dd, ruined_on = capital, capital, 0.0, None
    curve = []
    for t in sorted(taken, key=lambda t: t.exit_day):
        equity += t.net_pnl
        peak = max(peak, equity)
        if equity <= 0:  # delivery trades can't lose more than the account holds: the money is gone, the replay stops
            equity, max_dd, ruined_on = 0.0, -1.0, t.exit_day
            curve.append((t.exit_day.isoformat(), 0.0))
            break
        max_dd = min(max_dd, equity / peak - 1)
        curve.append((t.exit_day.isoformat(), round(equity, 2)))
    if len(curve) > 400:  # thin evenly (keep the whole period), always keeping the last point
        step = len(curve) / 400
        curve = [curve[int(i * step)] for i in range(400)] + [curve[-1]]
    first, last = min(t.entry_day for t in trades), max(t.exit_day for t in trades)
    years = max((last - first).days / 365.25, 0.1)
    gross_win = sum(t.net_pnl for t in wins)
    gross_loss = -sum(t.net_pnl for t in losses)
    return {
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades), 3),
        "avg_r": round(sum(rs) / len(rs), 3),
        # the same trades with brokerage and taxes added back: is the idea itself any good, or do charges sink it?
        "avg_r_before_charges": round(sum((t.net_pnl + t.charges) / ((t.entry - t.stop) * t.qty) for t in trades) / len(trades), 3),
        "avg_win_r": round(sum(t.r_multiple for t in wins) / len(wins), 3) if wins else None,
        "avg_loss_r": round(sum(t.r_multiple for t in losses) / len(losses), 3) if losses else None,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "avg_hold_days": round(sum(t.hold_days for t in trades) / len(trades), 1),
        "avg_charges": round(sum(t.charges for t in trades) / len(trades), 2),
        "max_losing_streak": worst,
        "exits": {k: sum(1 for t in trades if t.exit_reason == k) for k in ("target", "stop", "time")},
        "period": [first.isoformat(), last.isoformat()],
        "portfolio": {
            "capital": capital,
            "max_positions": max_positions,
            "trades_taken": len(taken),
            "final_equity": round(equity, 2),
            "cagr": round((equity / capital) ** (1 / years) - 1, 4) if equity > 0 else -1.0,
            "max_drawdown": round(max_dd, 4),
            "ruined_on": ruined_on.isoformat() if ruined_on else None,
            "curve": curve,
        },
    }


def verdict(stats: dict, rules: dict) -> tuple[bool, str]:
    """Is this setup allowed to produce live ideas?"""
    bt = rules["backtest"]
    if stats.get("trades", 0) < bt["min_trades"]:
        return False, f"Only {stats.get('trades', 0)} past trades — at least {bt['min_trades']} needed to trust it"
    if stats["avg_r"] < bt["min_expectancy_r"]:
        return False, f"Lost money after costs in the past (average {stats['avg_r']:+.2f}R per trade)"
    return True, f"Made {stats['avg_r']:+.2f}R per trade on average after costs, over {stats['trades']} past trades"
