"""Intraday backtests: the three fixed setups on 6 years of 15-minute bars, judged only on 2024 onwards."""

from collections.abc import Callable
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IndexDaily, Instrument, SetupBacktest
from app.engines import intraday as eng
from app.engines.adjust import detect
from app.engines.backtest import position_size
from app.engines.costs import intraday_round_trip
from app.rules import load_rules
from app.services import strategy_versions, trading
from app.services.errors import JobSkipped
from app.services.intraday_data import daily_from_intraday
from app.services.intraday_data import load as load_intraday
from app.services.stock_data import load_bars

Progress = Callable[[int, int], None]
PREFIX = "intraday:"
COMPARE_CAPITAL = 100000  # also shown: the same trades with ₹1 lakh, where fixed charges weigh less


def _noop(_d: int, _t: int) -> None:
    pass


def rules() -> dict:
    return load_rules("intraday")


def _version(db: Session):
    return strategy_versions.get_or_create(db, "intraday", {"version": rules()["version"], "intraday": rules(), "costs": trading.cost_rules()})


def _market_ok(db: Session, sma: int) -> dict[date, bool]:
    """Day D → did the Nifty 50 close above its `sma`-day average on the session before D?"""
    rows = db.execute(select(IndexDaily.date, IndexDaily.close).where(IndexDaily.symbol == "NIFTY").order_by(IndexDaily.date)).all()
    s = pd.Series([r[1] for r in rows], index=pd.DatetimeIndex([r[0] for r in rows]), dtype=float)
    above = (s > s.rolling(sma).mean()).shift(1)
    return {d.date(): bool(v) for d, v in above.items() if not pd.isna(v)}


def _contexts(daily: pd.DataFrame, bars: pd.DataFrame, market_ok: dict[date, bool], trend_sma: int) -> dict[date, eng.DayContext]:
    """Pre-open facts for every session with 15-minute bars.

    Yesterday's close, high and low are taken from the 15-minute bars themselves, so they are on the same price basis as
    today's bars (these bars aren't split-adjusted; the daily candles are). The trend test uses the adjusted daily closes.
    Ex-dates — where yesterday's bars are on the old share count — are skipped, and so are first-bar volume averages for a
    month after one (the volumes aren't comparable)."""
    sess = daily_from_intraday(bars)
    events = {d for d, _ in detect(sess)}
    trend = daily["close"] > daily["close"].rolling(trend_sma).mean()
    avg_first = sess["first_volume"].shift(1).rolling(20, min_periods=10).mean()
    daily_dates = daily.index
    days = list(sess.index)
    out = {}
    for i in range(1, len(days)):
        d, prev = days[i], sess.iloc[i - 1]
        pos = daily_dates.searchsorted(d) - 1  # the last daily candle before this session
        if d in events or pos < 0:
            continue
        recent_split = any(d - timedelta(days=30) < e <= d for e in events)
        out[d.date()] = eng.DayContext(
            day=d.date(),
            prev_close=float(prev["close"]),
            prev_high=float(prev["high"]),
            prev_low=float(prev["low"]),
            trend_ok=bool(trend.iloc[pos]),
            market_ok=market_ok.get(d.date(), False),
            avg_first_volume=None if recent_split or pd.isna(avg_first.iloc[i]) else float(avg_first.iloc[i]),
        )
    return out


def _sessions(bars: pd.DataFrame):
    """Yield (day, DayBars) for each session in a stock's 15-minute history."""
    days = bars.index.normalize()
    starts = np.flatnonzero(np.r_[True, days[1:] != days[:-1]])
    ends = np.r_[starts[1:], len(bars)]
    times = [t.time() for t in bars.index]
    o, h, lo, c, v = (bars[k].to_numpy() for k in ("open", "high", "low", "close", "volume"))
    for a, b in zip(starts, ends):
        yield days[a].date(), eng.DayBars(times[a:b], o[a:b], h[a:b], lo[a:b], c[a:b], v[a:b])


def _at_capital(t: eng.IntradayTrade, capital: float, r: dict, costs: dict) -> float | None:
    """The same trade sized for a different account: its R after charges."""
    qty = position_size(t.entry, t.stop, capital, r["risk_per_trade"], r["max_position_share"])
    if qty < 1:
        return None
    gross = (t.exit - t.entry) * qty
    return (gross - intraday_round_trip(t.entry * qty, t.exit * qty, costs)) / ((t.entry - t.stop) * qty)


def run_intraday_backtests(db: Session, progress: Progress = _noop) -> str:
    r, costs, cap = rules(), trading.cost_rules(), trading.capital(db)
    setups = [k for k, v in r["setups"].items() if v.get("enabled", True)]
    universe = db.scalars(select(Instrument).where(Instrument.in_universe.is_(True)).order_by(Instrument.universe_rank)).all()
    market_ok = _market_ok(db, r["market_filter_sma"])
    trades: dict[str, list[eng.IntradayTrade]] = {k: [] for k in setups}
    used = 0
    for n, inst in enumerate(universe):
        bars = load_intraday(inst.symbol)
        daily = load_bars(db, inst.id)
        if bars.empty or len(daily) < 60:
            continue
        used += 1
        ctxs = _contexts(daily, bars, market_ok, r["setups"]["orb"]["trend_sma"])
        for day, day_bars in _sessions(bars):
            ctx = ctxs.get(day)
            if ctx is None:
                continue
            for k in setups:
                t = eng.simulate(inst.symbol, k, ctx, day_bars, r, costs, cap)
                if t:
                    trades[k].append(t)
        progress(n + 1, len(universe))
    if not used:
        raise JobSkipped("Waiting for 15-minute price history")
    version = _version(db)
    b0, b1 = (date.fromisoformat(x) for x in r["periods"]["build"])
    t0, t1 = (date.fromisoformat(x) for x in r["periods"]["test"])
    lines = []
    for k in setups:
        build = [t for t in trades[k] if b0 <= t.day <= b1]
        test = [t for t in trades[k] if t0 <= t.day <= t1]
        sb, st = eng.summarise(build, r["max_trades_per_day"]), eng.summarise(test, r["max_trades_per_day"])
        alt = [x for x in (_at_capital(t, COMPARE_CAPITAL, r, costs) for t in test) if x is not None]
        ok, why = eng.verdict(sb, st, r)
        stats = {
            "build": sb,
            "test": st,
            "test_avg_r_at_1_lakh": round(sum(alt) / len(alt), 3) if alt else None,
            "recent": [t.__dict__ | {"day": t.day.isoformat()} for t in sorted(test, key=lambda t: (t.day, t.entry_time))[-15:]],
        }
        db.add(SetupBacktest(setup=PREFIX + k, strategy_version_id=version.id, capital=cap, universe_size=used, stats_json=stats, allowed=ok, verdict=why))
        lines.append(f"{r['setups'][k]['label']}: {'ON' if ok else 'OFF'} ({why})")
    db.commit()
    return "; ".join(lines)


def latest(db: Session) -> dict[str, SetupBacktest]:
    out: dict[str, SetupBacktest] = {}
    for row in db.scalars(select(SetupBacktest).where(SetupBacktest.setup.like(PREFIX + "%")).order_by(SetupBacktest.id.desc())):
        out.setdefault(row.setup[len(PREFIX):], row)
    return out
