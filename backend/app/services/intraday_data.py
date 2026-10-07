"""15-minute price history for the trading universe.

Stored as one compressed file per stock in data/intraday/ (not in the database): ~25 bars a day since 2020 for 200 stocks
is millions of rows that can always be downloaded again, so they stay out of the nightly database backup.

Two Groww feeds are combined (see connectors/groww.py): the backtesting feed for old history, and the candle-data feed
for the newest sessions, because the backtesting feed runs days behind and its newest sessions can be incomplete. Day by
day, whichever answer covers more of the session is kept.

These bars are NOT adjusted for splits and bonuses (the daily candles in the database are). Anything that compares one
session with the next should take both from here — see daily_from_intraday().
"""

from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_config
from app.connectors.groww import GrowwBusy, GrowwNoDataAccess, IntradayBar
from app.connectors.http import SourceUnavailable
from app.db.models import Instrument
from app.services import groww_service
from app.services.errors import JobSkipped
from app.services.stock_data import now_ist, rules

Progress = Callable[[int, int], None]
COLUMNS = ["open", "high", "low", "close", "volume"]
FULL_SESSION_BARS = 25  # 09:15 … 15:15
RECENT_FEED_DAYS = 80  # the candle-data feed keeps 15-minute bars for about 3 months
HEAL_WINDOW_DAYS = 45  # sessions this recent are fetched again if they look incomplete
HEALED_MARKER = ".recent-feed-v1"  # written once every stock's recent sessions have been re-read from the candle-data feed


def _noop(_d: int, _t: int) -> None:
    pass


def folder() -> Path:
    d = get_config().data_dir / "intraday"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(symbol: str) -> Path:
    return folder() / f"{symbol}.npz"


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], name="ts"))


def load(symbol: str) -> pd.DataFrame:
    """15-minute bars indexed by bar start time (IST), columns open/high/low/close/volume. Empty if never downloaded."""
    p = _path(symbol)
    if not p.exists():
        return _empty()
    with np.load(p) as z:
        return pd.DataFrame({k: z[k] for k in COLUMNS}, index=pd.DatetimeIndex(z["ts"].astype("datetime64[s]"), name="ts"))


def _save(symbol: str, df: pd.DataFrame) -> None:
    tmp = _path(symbol).with_suffix(".tmp.npz")
    np.savez_compressed(
        tmp,
        ts=df.index.values.astype("datetime64[s]").astype("int64"),
        **{k: df[k].to_numpy(dtype="float64") for k in ("open", "high", "low", "close")},
        volume=df["volume"].to_numpy(dtype="int64"),
    )
    tmp.replace(_path(symbol))


def _frame(bars: list[IntradayBar]) -> pd.DataFrame:
    if not bars:
        return _empty()
    return pd.DataFrame(
        {"open": [b.open for b in bars], "high": [b.high for b in bars], "low": [b.low for b in bars], "close": [b.close for b in bars], "volume": [b.volume for b in bars]},
        index=pd.DatetimeIndex([b.ts for b in bars], name="ts"),
    )


def merge_days(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Day by day: the new bars replace the stored ones when they cover at least as much of the session."""
    if new.empty:
        return old
    new = new[~new.index.duplicated(keep="last")].sort_index()
    if old.empty:
        return new
    old_days, new_days = old.index.normalize(), new.index.normalize()
    had = old.groupby(old_days).size()
    take = [d for d, n in new.groupby(new_days).size().items() if n >= had.get(d, 0)]
    return pd.concat([old[~old_days.isin(take)], new[new_days.isin(take)]]).sort_index()


def _same(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """Same bars, whatever the time resolution or number types the two frames happen to use."""
    if len(a) != len(b):
        return False
    same_times = np.array_equal(a.index.values.astype("datetime64[s]"), b.index.values.astype("datetime64[s]"))
    return same_times and np.array_equal(a[COLUMNS].to_numpy(dtype="float64"), b[COLUMNS].to_numpy(dtype="float64"))


def daily_from_intraday(df: pd.DataFrame) -> pd.DataFrame:
    """Per session, from the bars themselves: open, high, low, close, volume, the first bar's volume and the bar count."""
    if df.empty:
        return pd.DataFrame(columns=[*COLUMNS, "first_volume", "bars"])
    g = df.groupby(df.index.normalize())
    return pd.DataFrame(
        {
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "volume": g["volume"].sum(),
            "first_volume": g["volume"].first(),
            "bars": g["open"].size(),
        }
    )


def tail_start(have: pd.DataFrame, today: date, heal: bool = False) -> date:
    """Where to start asking the candle-data feed: the first incomplete-looking session of the last few weeks (or, when
    healing, the start of that window), otherwise the last saved day — re-read in case it was saved mid-session."""
    floor = today - timedelta(days=RECENT_FEED_DAYS)
    if have.empty:
        return floor
    window = today - timedelta(days=HEAL_WINDOW_DAYS)
    last = have.index[-1].date()
    if heal:
        return max(floor, min(window, last))
    recent = have[have.index >= pd.Timestamp(window)]
    counts = recent.groupby(recent.index.normalize()).size()
    short = counts[counts < FULL_SESSION_BARS]
    return max(floor, min(short.index[0].date(), last) if len(short) else last)


def sync_intraday(db: Session, progress: Progress = _noop) -> str:
    """Bring every stock's 15-minute bars up to the latest session: old history from the backtesting feed the first time,
    then the newest sessions from the candle-data feed."""
    universe = db.scalars(select(Instrument).where(Instrument.in_universe.is_(True)).order_by(Instrument.universe_rank)).all()
    if not universe:
        raise JobSkipped("Waiting for the stock ranking (trading universe) to finish")
    client = groww_service.client(db)
    start = date.fromisoformat(rules()["universe"]["history_start"])
    today = now_ist().date()
    marker = folder() / HEALED_MARKER
    heal = not marker.exists()
    updated = failed = 0
    for n, inst in enumerate(universe):
        try:
            have = load(inst.symbol)
            merged = have
            if have.empty or have.index[-1].date() < today - timedelta(days=RECENT_FEED_DAYS):
                deep_from = start if have.empty else have.index[-1].date()
                merged = merge_days(merged, _frame(client.intraday_candles(inst.groww_symbol, deep_from, today)))
            fresh = _frame(client.recent_intraday_candles(inst.groww_symbol, max(start, tail_start(merged, today, heal)), today))
            merged = merge_days(merged, fresh)
            if len(merged) and not _same(merged, have):
                _save(inst.symbol, merged)
                updated += 1
        except (GrowwNoDataAccess, GrowwBusy):
            raise  # files already saved are kept; the next run carries on from there
        except SourceUnavailable:
            failed += 1
        progress(n + 1, len(universe))
    if heal and not failed:
        marker.write_text("recent sessions re-read from the candle-data feed\n", encoding="utf-8")
    return f"15-minute bars updated for {updated} of {len(universe)} stocks ({failed} failed)"


def missing_intraday(db: Session) -> int:
    """Universe stocks with no 15-minute history file yet."""
    syms = db.scalars(select(Instrument.symbol).where(Instrument.in_universe.is_(True))).all()
    return sum(1 for s in syms if not _path(s).exists())
