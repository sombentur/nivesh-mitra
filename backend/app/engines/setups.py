"""Trade setups (rules/trading.yaml → setups). Each returns signals with entry range, stop-loss and target.

A signal on day D means: "buy on the next trading day within the entry range". Delivery trades only.
"""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.engines.indicators import add_indicators


@dataclass
class Signal:
    setup: str
    day: date
    close: float
    entry_low: float
    entry_high: float
    stop: float
    target: float
    max_hold_days: int
    reasons: list[str] = field(default_factory=list)

    @property
    def risk_per_share(self) -> float:
        return self.close - self.stop

    @property
    def reward_risk_worst(self) -> float:
        """Reward : risk if you buy at the top of the entry range (the least favourable fill)."""
        return (self.target - self.entry_high) / (self.entry_high - self.stop)


def prepare(df: pd.DataFrame, rules: dict) -> pd.DataFrame:
    s = rules["setups"]
    return add_indicators(
        df,
        touch_days=s["trend_pullback"]["rules"]["touched_20dma_within_days"],
        breakout_days=s["volume_breakout"]["rules"]["breakout_days"],
        swing_days=s["trend_pullback"]["rules"]["stop_swing_days"],
    )


def _finish(setup: str, row, day, entry_low, entry_high, stop, target_r, hold, cfg, min_rr, reasons) -> Signal | None:
    """Risk and target are measured from the TOP of the entry range, so even the worst fill keeps the promised R:R."""
    close = float(row.close)
    worst_risk = entry_high - stop
    if worst_risk <= 0 or not (cfg["min_risk_pct"] <= worst_risk / entry_high <= cfg["max_risk_pct"]):
        return None
    target = entry_high + target_r * worst_risk
    sig = Signal(setup, day, close, round(entry_low, 2), round(entry_high, 2), round(stop, 2), round(target, 2), hold, reasons)
    return sig if sig.reward_risk_worst >= min_rr - 1e-6 else None


def trend_pullback(ind: pd.DataFrame, cfg: dict, min_rr: float) -> list[Signal]:
    r = cfg["rules"]
    mask = (
        (ind["close"] > ind["sma200"])
        & (ind["sma50"] > ind["sma200"])
        & (ind["low_to_sma20_min"] <= 1 + r["touch_tolerance"])
        & (ind["close"] > ind["sma20"])
        & ind["rsi14"].between(r["rsi_min"], r["rsi_max"])
        & ind["green"].astype(bool)
    )
    out = []
    for day, row in ind[mask].iterrows():
        stop = max(row.close - r["stop_atr"] * row.atr14, row.low_swing - r["stop_swing_buffer_atr"] * row.atr14)
        reasons = [
            f"Above its 200-day average (₹{row.sma200:,.0f}) and the 50-day is above the 200-day: a steady uptrend",
            f"Dipped to its 20-day average (₹{row.sma20:,.0f}) in the last {r['touched_20dma_within_days']} days and closed back above it",
            f"RSI {row.rsi14:.0f}: cooled off, not overheated",
        ]
        sig = _finish(
            "trend_pullback", row, day.date(), row.close * (1 - r["entry_band"]), row.close * (1 + r["entry_band"]),
            stop, r["target_r"], r["max_hold_days"], r, min_rr, reasons,
        )
        if sig:
            out.append(sig)
    return out


def volume_breakout(ind: pd.DataFrame, cfg: dict, min_rr: float) -> list[Signal]:
    r = cfg["rules"]
    mask = (
        (ind["close"] > ind["high_prev_n"])
        & (ind["volume"] >= r["volume_multiple"] * ind["vol20_prev"])
        & (ind["sma50"] > ind["sma200"])
        & (ind["close"] > ind["sma50"])
        & (ind["close_in_range"] >= r["close_in_top_of_range"])
        & (ind["rsi14"] < r["rsi_max"])
    )
    out = []
    for day, row in ind[mask].iterrows():
        stop = row.high_prev_n - r["stop_below_breakout_atr"] * row.atr14
        if (row.close - stop) / row.close < r["min_risk_pct"]:
            stop = row.close - r["fallback_stop_atr"] * row.atr14
        reasons = [
            f"Closed at ₹{row.close:,.2f}, above its {r['breakout_days']}-day high of ₹{row.high_prev_n:,.2f}",
            f"Volume {row.volume / row.vol20_prev:.1f}× its 20-day average: strong interest",
            f"Uptrend: above its 50-day average, which is above the 200-day",
        ]
        sig = _finish(
            "volume_breakout", row, day.date(), row.close, row.close * (1 + r["entry_band_up"]),
            stop, r["target_r"], r["max_hold_days"], r, min_rr, reasons,
        )
        if sig:
            out.append(sig)
    return out


SETUPS = {"trend_pullback": trend_pullback, "volume_breakout": volume_breakout}


def find_signals(ind: pd.DataFrame, rules: dict, only_last_day: bool = False) -> list[Signal]:
    data = ind.iloc[-1:] if only_last_day else ind
    min_rr = rules["risk"]["min_reward_risk"]
    out: list[Signal] = []
    for key, fn in SETUPS.items():
        cfg = rules["setups"][key]
        if cfg.get("enabled", True):
            out.extend(fn(data, cfg, min_rr))
    return sorted(out, key=lambda s: s.day)
