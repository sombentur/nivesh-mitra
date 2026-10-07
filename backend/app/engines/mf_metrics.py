"""Fund metrics from daily NAVs (doc 03 §C2). Pure functions over pandas Series indexed by date.

Conventions: returns are fractions (0.12 = 12%). Drawdowns are negative (−0.35 = fell 35%).
"""

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

TRADING_DAYS = 252
GRID_STEP_DAYS = 7  # rolling windows are sampled weekly, all funds on the same dates


def to_series(points: list[tuple[date, float]]) -> pd.Series:
    if not points:
        return pd.Series(dtype=float)
    idx = pd.DatetimeIndex([p[0] for p in points])
    return pd.Series([p[1] for p in points], index=idx, dtype=float).sort_index()


def _calendar(s: pd.Series, as_of: pd.Timestamp) -> pd.Series:
    """Daily calendar series, carrying the last NAV over weekends/holidays (at most 7 days)."""
    full = pd.date_range(s.index[0], max(as_of, s.index[-1]), freq="D")
    return s.reindex(full).ffill(limit=7)


def grid(as_of: pd.Timestamp, lookback_years: int) -> pd.DatetimeIndex:
    """Common weekly end-dates, counting back from as_of, so funds can be compared date by date."""
    start = as_of - pd.DateOffset(years=lookback_years)
    return pd.date_range(end=as_of, start=start, freq=f"{GRID_STEP_DAYS}D")


def rolling_cagr(s: pd.Series, years: float, ends: pd.DatetimeIndex) -> pd.Series:
    """CAGR of every `years`-long window ending on each date in `ends` (NaN where history is too short)."""
    if s.empty:
        return pd.Series(index=ends, dtype=float)
    cal = _calendar(s, ends[-1])
    lag = int(round(365.25 * years))
    ratio = cal / cal.shift(lag)
    r = ratio.reindex(ends)
    return r ** (1 / years) - 1 if years >= 1 else r - 1


def point_cagr(s: pd.Series, years: float, as_of: pd.Timestamp) -> float | None:
    r = rolling_cagr(s, years, pd.DatetimeIndex([as_of])).iloc[0]
    return None if pd.isna(r) else float(r)


def _window(s: pd.Series, years: float, as_of: pd.Timestamp) -> pd.Series:
    return s[(s.index > as_of - pd.DateOffset(days=int(365.25 * years))) & (s.index <= as_of)]


def volatility(s: pd.Series, years: float, as_of: pd.Timestamp) -> float | None:
    rets = _window(s, years, as_of).pct_change().dropna()
    if len(rets) < TRADING_DAYS * years * 0.8:
        return None
    return float(rets.std() * math.sqrt(TRADING_DAYS))


def downside_deviation(s: pd.Series, years: float, as_of: pd.Timestamp, rf: float) -> float | None:
    rets = _window(s, years, as_of).pct_change().dropna()
    if len(rets) < TRADING_DAYS * years * 0.8:
        return None
    shortfall = np.minimum(rets - rf / TRADING_DAYS, 0)
    return float(math.sqrt((shortfall**2).mean()) * math.sqrt(TRADING_DAYS))


def max_drawdown(s: pd.Series, years: float, as_of: pd.Timestamp) -> float | None:
    w = _window(s, years, as_of)
    if len(w) < TRADING_DAYS * min(years, 1) * 0.8:
        return None
    return float((w / w.cummax() - 1).min())


def downside_capture(s: pd.Series, bench: pd.Series, years: float, as_of: pd.Timestamp) -> float | None:
    """How much of the benchmark's fall the fund took, in months when the benchmark fell (1.0 = the same)."""
    f = _window(s, years, as_of).resample("ME").last().pct_change()
    b = _window(bench, years, as_of).resample("ME").last().pct_change()
    both = pd.concat([f, b], axis=1, keys=["f", "b"]).dropna()
    down = both[both["b"] < 0]
    if len(down) < 6:
        return None
    return float(down["f"].mean() / down["b"].mean())


def worst_period_return(s: pd.Series, days: int, years: float, as_of: pd.Timestamp) -> float | None:
    """Worst return over any `days`-calendar-day stretch in the last `years` (catches credit accidents)."""
    w = _window(s, years, as_of)
    if len(w) < 60:
        return None
    cal = _calendar(w, as_of)
    return float((cal / cal.shift(days) - 1).min())


def share_above(a: pd.Series, b: pd.Series) -> float | None:
    """Fraction of dates where a > b, over dates where both exist."""
    both = pd.concat([a, b], axis=1).dropna()
    if len(both) < 10:
        return None
    return float((both.iloc[:, 0] > both.iloc[:, 1]).mean())


def tracking(s: pd.Series, ref: pd.Series, years: float, as_of: pd.Timestamp) -> tuple[float | None, float | None]:
    """(tracking error, tracking difference) of an index fund against the typical fund tracking the same index."""
    f = _window(s, years, as_of).pct_change()
    r = _window(ref, years, as_of).pct_change()
    both = pd.concat([f, r], axis=1).dropna()
    if len(both) < TRADING_DAYS * years * 0.7:
        return None, None
    te = float((both.iloc[:, 0] - both.iloc[:, 1]).std() * math.sqrt(TRADING_DAYS))
    fc, rc = point_cagr(s, years, as_of), point_cagr(ref, years, as_of)
    td = None if fc is None or rc is None else fc - rc
    return te, td


def median_series(series: list[pd.Series]) -> pd.Series:
    if not series:
        return pd.Series(dtype=float)
    return pd.concat(series, axis=1).median(axis=1, skipna=True)


def history_years(s: pd.Series, as_of: pd.Timestamp) -> float:
    return 0.0 if s.empty else (as_of - s.index[0]).days / 365.25


@dataclass
class Rolling:
    rr1: pd.Series
    rr3: pd.Series
    rr5: pd.Series
    rr7: pd.Series


def rolling_set(s: pd.Series, ends: pd.DatetimeIndex) -> Rolling:
    return Rolling(*(rolling_cagr(s, y, ends) for y in (1, 3, 5, 7)))


def _med(x: pd.Series) -> float | None:
    x = x.dropna()
    return float(x.median()) if len(x) >= 26 else None  # at least ~6 months of weekly windows


def _q(x: pd.Series, q: float) -> float | None:
    x = x.dropna()
    return float(x.quantile(q)) if len(x) >= 26 else None


def fund_metrics(s: pd.Series, as_of: pd.Timestamp, ends: pd.DatetimeIndex, rf: float, bench: pd.Series | None) -> tuple[dict, Rolling]:
    """Everything that doesn't need peers. Peer-relative metrics (beat_cat, tracking) are added by the scorer."""
    roll = rolling_set(s, ends)
    m: dict[str, float | None] = {
        "history_years": round(history_years(s, as_of), 2),
        "return_1y": point_cagr(s, 1, as_of),
        "cagr_3y": point_cagr(s, 3, as_of),
        "cagr_5y": point_cagr(s, 5, as_of),
        "rr1_med": _med(roll.rr1),
        "rr3_med": _med(roll.rr3),
        "rr5_med": _med(roll.rr5),
        "rr7_med": _med(roll.rr7),
        "rr3_p10": _q(roll.rr3, 0.10),
        "rr3_p90": _q(roll.rr3, 0.90),
        "vol_3y": volatility(s, 3, as_of),
        "maxdd_5y": max_drawdown(s, 5, as_of),
        "worst_1m": worst_period_return(s, 30, 3, as_of),
    }
    dd = downside_deviation(s, 3, as_of, rf)
    c3 = m["cagr_3y"]
    m["sharpe_3y"] = (c3 - rf) / m["vol_3y"] if c3 is not None and m["vol_3y"] else None
    m["sortino_3y"] = (c3 - rf) / dd if c3 is not None and dd else None
    if bench is not None and not bench.empty:
        broll = rolling_cagr(bench, 3, ends)
        m["beat_bench_3y"] = share_above(roll.rr3, broll)
        m["downcap_3y"] = downside_capture(s, bench, 3, as_of)
    return m, roll


def cost_gap(direct: pd.Series, regular: pd.Series, as_of: pd.Timestamp) -> float | None:
    """Yearly return gap between a fund's Direct and Regular plans — what the Regular plan's commission costs you."""
    for years in (3, 1):
        d, r = point_cagr(direct, years, as_of), point_cagr(regular, years, as_of)
        if d is not None and r is not None:
            return max(0.0, d - r)
    return None
