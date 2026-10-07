"""Stocks: Groww's instrument list, the liquid trading universe, and daily price history.

Daily candles come from Groww's candle-data feed, which is already adjusted for splits and bonuses (connectors/groww.py).
When a new split or bonus happens Groww re-bases the stock's whole history, so the daily update checks for that and
downloads the history again — every stored row for a stock is always on one price basis.
"""

import csv
import io
import re
import statistics
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.connectors.groww import Candle, GrowwBusy, GrowwNoDataAccess
from app.connectors.http import SourceUnavailable, get_text
from app.db.base import utcnow
from app.db.models import IndexDaily, Instrument, PriceDaily
from app.engines import holidays
from app.rules import load_rules
from app.services import groww_service
from app.services.errors import JobSkipped
from app.services.mf_data import set_status

Progress = Callable[[int, int], None]
INSTRUMENTS_URL = "https://growwapi-assets.groww.in/instruments/instrument.csv"
# Indices with full history since 2020 (used by backtests and the market mood)…
INDICES = ["NIFTY", "NIFTY500", "NIFTYMIDCAP150", "INDIAVIX"]
# …and ones shown in the ticker, index widgets and sector heat-map (about a year of history is enough).
DISPLAY_INDICES = {
    **{s: f"NSE-{s}" for s in (
        "BANKNIFTY", "FINNIFTY", "NIFTYJR", "NIFTYMIDCAP", "NIFTYSMALL", "NIFTYIT", "NIFTYAUTO", "NIFTYPHARMA", "NIFTYFMCG",
        "NIFTYMETAL", "NIFTYREALTY", "NIFTYPSUBANK", "NIFTYPVTBANK", "NIFTYMEDIA", "NIFTYCDTY",
    )},
    **{s: f"BSE-{s}" for s in ("SENSEX", "BANKEX", "BSE100")},  # Groww has no history for BSE Midcap/Smallcap
}
DISPLAY_HISTORY_DAYS = 400
BSE_TAPE_SIZE = 30  # the largest stocks' BSE prices, for the BSE ticker (stored in index_daily as "BSE:SYMBOL")
SOURCE_PRICES = "groww_prices"
IST = ZoneInfo("Asia/Kolkata")
SESSION_FINAL = time(15, 40)  # a day's candle is final a few minutes after the 3:30 PM close
REBASED_TOLERANCE = 0.002  # an older close that moved by more than 0.2% means Groww re-based the history


def _noop(_d: int, _t: int) -> None:
    pass


def rules() -> dict:
    return load_rules("trading")


def now_ist() -> datetime:
    return datetime.now(IST)


def finished(candles: list[Candle]) -> list[Candle]:
    """Completed sessions only: until the market has closed, today's candle is still changing and isn't a day's result."""
    now = now_ist()
    if candles and candles[-1].day >= now.date() and now.time() < SESSION_FINAL:
        return candles[:-1]
    return candles


def _upsert(db: Session, model, values: list[dict], keys: list[str]) -> None:
    """Insert, or overwrite what's stored: Groww's later answer wins (an evening re-download corrects a provisional
    candle). An empty open never wipes one that is already known."""
    if not values:
        return
    for i in range(0, len(values), 5000):
        stmt = sqlite_insert(model)
        update = {c: getattr(stmt.excluded, c) for c in values[0] if c not in keys}
        if "open" in update:
            update["open"] = func.coalesce(stmt.excluded.open, getattr(model, "open"))
        db.execute(stmt.on_conflict_do_update(index_elements=keys, set_=update), values[i : i + 5000])


def store_candles(db: Session, inst: Instrument, candles: list[Candle]) -> None:
    candles = finished(candles)
    _upsert(
        db,
        PriceDaily,
        [dict(instrument_id=inst.id, date=c.day, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume) for c in candles],
        ["instrument_id", "date"],
    )
    if candles:
        inst.history_start = min(filter(None, [inst.history_start, candles[0].day]))
        inst.history_end = max(filter(None, [inst.history_end, candles[-1].day]))


def replace_history(db: Session, inst: Instrument, candles: list[Candle]) -> None:
    """Swap a stock's whole stored history for a fresh download, so every row is on the same (adjusted) price basis."""
    candles = finished(candles)
    had = db.scalar(select(func.count()).select_from(PriceDaily).where(PriceDaily.instrument_id == inst.id)) or 0
    if len(candles) < 0.8 * had:
        raise SourceUnavailable(f"Groww returned only {len(candles)} days of history for {inst.symbol} (had {had}); keeping what is stored")
    db.execute(delete(PriceDaily).where(PriceDaily.instrument_id == inst.id))
    inst.history_start = inst.history_end = None
    store_candles(db, inst, candles)


def rebased(db: Session, inst: Instrument, candles: list[Candle]) -> bool:
    """After a split or bonus Groww re-bases all of a stock's past prices. If one of the oldest candles just fetched no
    longer matches the stored close for that day, the stored history is on the old basis and must be downloaded again."""
    for c in candles[:3]:
        stored = db.scalar(select(PriceDaily.close).where(PriceDaily.instrument_id == inst.id, PriceDaily.date == c.day))
        if stored:
            return abs(c.close / stored - 1) > REBASED_TOLERANCE
    return False


def sync_instruments(db: Session, progress: Progress = _noop) -> str:
    """Groww's public instrument list (no login needed): every NSE cash-market 'EQ' series stock."""
    text = get_text(INSTRUMENTS_URL, timeout=120)
    reader = csv.DictReader(io.StringIO(text))
    wanted = {}
    for row in reader:
        if row.get("exchange") == "NSE" and row.get("segment") == "CASH" and row.get("instrument_type") == "EQ" and row.get("series") == "EQ":
            wanted[row["trading_symbol"]] = row
    if len(wanted) < 500:
        raise SourceUnavailable(f"Groww's instrument list looks incomplete ({len(wanted)} NSE stocks)")
    existing = {i.symbol: i for i in db.scalars(select(Instrument))}
    for sym, row in wanted.items():
        inst = existing.get(sym) or Instrument(symbol=sym)
        inst.groww_symbol, inst.isin, inst.name, inst.series = row["groww_symbol"], row.get("isin") or None, row.get("name") or sym, "EQ"
        inst.is_active, inst.updated_at = True, utcnow()
        db.add(inst)
    for sym, inst in existing.items():
        if sym not in wanted:
            inst.is_active, inst.in_universe = False, False
    db.commit()
    return f"{len(wanted)} NSE stocks in Groww's list"


def is_company_share(inst: Instrument, exclude: re.Pattern) -> bool:
    """ETFs trade in the same 'EQ' series as shares. Their ISINs start with INF (fund units; shares start with INE), and
    Groww often names them by symbol alone ("LIQUIDBEES"), so the name check isn't enough on its own."""
    return not (inst.isin or "").upper().startswith("INF") and not exclude.search(inst.name or "")


def scan_universe(db: Session, progress: Progress = _noop) -> str:
    """Rank every NSE stock by how much it trades; keep the most liquid ones as the trading universe."""
    u = rules()["universe"]
    client = groww_service.client(db)
    exclude = re.compile(u["exclude_name_pattern"])
    candidates = [i for i in db.scalars(select(Instrument).where(Instrument.is_active.is_(True))) if is_company_share(i, exclude)]
    today = now_ist().date()
    start = today - timedelta(days=int(u["liquidity_days"] * 1.6))
    enough = int(u["liquidity_days"] * 0.8)
    ranked: list[tuple[float, Instrument]] = []

    def check(inst: Instrument, reuse: bool = True) -> bool:
        """True when this stock's data is complete (or it's genuinely short of history, e.g. newly listed)."""
        stored = _stored_since(db, inst, start) if reuse and inst.history_end and inst.history_end >= today - timedelta(days=4) else []
        if len(stored) >= enough:
            candles = stored  # already downloaded (a scan that was interrupted, or the daily update): don't ask Groww again
        else:
            candles = finished(client.daily_candles(inst.groww_symbol, start, today))  # GrowwBusy / NoDataAccess propagate
            store_candles(db, inst, candles)
            db.commit()  # save per stock: never hold the database while waiting on Groww
        recent = candles[-u["liquidity_days"] :]
        if len(recent) >= enough and recent[-1].close >= u["min_price"]:
            value = statistics.median(c.close * c.volume for c in recent)
            inst.median_traded_value = value
            if value >= u["min_median_traded_value"]:
                ranked.append((value, inst))
        return len(recent) >= enough

    short: list[Instrument] = []
    for n, inst in enumerate(candidates):
        try:
            if not check(inst):
                short.append(inst)
        except (GrowwNoDataAccess, GrowwBusy):
            raise
        except SourceUnavailable:
            short.append(inst)
        if n % 50 == 0:
            progress(n, len(candidates))
    # Second pass: a short answer can be a hiccup at Groww's end — ask once more before ranking without it.
    for inst in short:
        try:
            check(inst, reuse=False)
        except (GrowwNoDataAccess, GrowwBusy):
            raise
        except SourceUnavailable:
            continue
    ranked.sort(key=lambda x: x[0], reverse=True)
    chosen = {inst.id for _, inst in ranked[: u["size"]]}
    for rank, (_, inst) in enumerate(ranked, start=1):
        inst.in_universe = inst.id in chosen
        inst.universe_rank = rank if inst.id in chosen else None
    for inst in candidates:
        if inst.id not in chosen:
            inst.in_universe, inst.universe_rank = False, None
    db.commit()
    return f"Scanned {len(candidates)} stocks ({len(short)} needed a second look); trading universe = {len(chosen)} most-traded"


def _stored_since(db: Session, inst: Instrument, start: date) -> list[Candle]:
    rows = db.execute(
        select(PriceDaily.date, PriceDaily.open, PriceDaily.high, PriceDaily.low, PriceDaily.close, PriceDaily.volume)
        .where(PriceDaily.instrument_id == inst.id, PriceDaily.date >= start)
        .order_by(PriceDaily.date)
    ).all()
    return [Candle(*r) for r in rows]


def universe_missing_history(db: Session) -> int:
    """Universe stocks whose history from 2020 hasn't been downloaded yet."""
    # Recorded per stock: one listed in 2023 is complete with history from 2023.
    return db.scalar(
        select(func.count(Instrument.id)).where(
            Instrument.in_universe.is_(True), Instrument.history_error.is_(None), Instrument.history_complete.is_(False)
        )
    ) or 0


def backfill_prices(db: Session, progress: Progress = _noop) -> str:
    """Full daily history (from 2020) for the universe and the market indices."""
    start = date.fromisoformat(rules()["universe"]["history_start"])
    universe = db.scalars(select(Instrument).where(Instrument.in_universe.is_(True))).all()
    if not universe:
        raise JobSkipped("Waiting for the stock ranking (trading universe) to finish — this starts by itself after it")
    client = groww_service.client(db)
    today = now_ist().date()
    todo = [i for i in universe if not i.history_complete]
    for n, inst in enumerate(todo):
        try:
            replace_history(db, inst, client.daily_candles(inst.groww_symbol, start, today))
            inst.history_error, inst.history_complete = None, True
        except (GrowwNoDataAccess, GrowwBusy):
            raise  # finished stocks are kept; the job resumes where it stopped next time
        except SourceUnavailable as exc:
            inst.history_error = str(exc)[:300]
        db.commit()
        progress(n + 1, len(todo))
    for sym in INDICES:
        have = db.scalar(select(func.min(IndexDaily.date)).where(IndexDaily.symbol == sym))
        if have is None or have > start + timedelta(days=10):
            _store_index(db, sym, client.daily_candles(f"NSE-{sym}", start, today))
    db.commit()
    return f"Downloaded price history for {len(todo)} stocks and {len(INDICES)} indices"


def _store_index(db: Session, sym: str, candles: list[Candle]) -> None:
    candles = finished(candles)
    _upsert(db, IndexDaily, [dict(symbol=sym, date=c.day, open=c.open, high=c.high, low=c.low, close=c.close) for c in candles], ["symbol", "date"])


def update_daily_prices(db: Session, progress: Progress = _noop) -> str:
    """After the market closes: the last few sessions for the universe, open paper trades and the indices."""
    from app.db.models import PaperTrade  # local import: avoids a cycle with the trading service

    client = groww_service.client(db)
    today = now_ist().date()
    start = today - timedelta(days=10)
    history_start = date.fromisoformat(rules()["universe"]["history_start"])
    held = select(PaperTrade.instrument_id).where(PaperTrade.status.in_(("pending", "open")))
    insts = db.scalars(select(Instrument).where(Instrument.in_universe.is_(True) | Instrument.id.in_(held))).all()
    try:
        for n, inst in enumerate(insts):
            try:
                candles = client.daily_candles(inst.groww_symbol, start, today)
                if rebased(db, inst, candles):  # a split or bonus: get the whole history on the new basis
                    replace_history(db, inst, client.daily_candles(inst.groww_symbol, history_start, today))
                else:
                    store_candles(db, inst, candles)
            except (GrowwNoDataAccess, GrowwBusy):
                raise
            except SourceUnavailable:
                continue
            db.commit()
            if n % 25 == 0:
                progress(n, len(insts))
        for sym in INDICES:
            _store_index(db, sym, client.daily_candles(f"NSE-{sym}", start, today))
        for sym, groww_symbol in DISPLAY_INDICES.items():
            have = db.scalar(select(func.min(IndexDaily.date)).where(IndexDaily.symbol == sym))
            first = today - timedelta(days=DISPLAY_HISTORY_DAYS) if have is None or have > today - timedelta(days=DISPLAY_HISTORY_DAYS - 30) else start
            _store_index(db, sym, client.daily_candles(groww_symbol, first, today))
        update_bse_tape(db, client, today)
    except SourceUnavailable as exc:
        set_status(db, SOURCE_PRICES, False, str(exc))
        db.commit()
        raise
    set_status(db, SOURCE_PRICES, True, sla_minutes=60 * 30)
    db.commit()
    return f"Prices updated for {len(insts)} stocks (latest session {latest_session(db)})"


def update_bse_tape(db: Session, client, today: date) -> int:
    """BSE daily closes for the largest universe stocks (most trade under the same symbol on BSE; any that don't are skipped)."""
    top = db.scalars(select(Instrument.symbol).where(Instrument.in_universe.is_(True)).order_by(Instrument.universe_rank).limit(BSE_TAPE_SIZE)).all()
    done = 0
    for sym in top:
        key = f"BSE:{sym}"
        have = db.scalar(select(func.max(IndexDaily.date)).where(IndexDaily.symbol == key))
        first = today - timedelta(days=30) if have is None else today - timedelta(days=10)
        try:
            _store_index(db, key, client.daily_candles(f"BSE-{sym}", first, today))
            done += 1
        except (GrowwNoDataAccess, GrowwBusy):
            raise
        except SourceUnavailable:
            continue
    db.commit()
    return done


def prices_behind(db: Session) -> bool:
    """True when a finished session's prices haven't been downloaded yet (weekends and listed holidays are skipped)."""
    latest = latest_session(db)
    return latest is None or latest < holidays.last_completed_session(now_ist())


def latest_session(db: Session) -> date | None:
    return db.scalar(select(func.max(IndexDaily.date)).where(IndexDaily.symbol == "NIFTY")) or db.scalar(select(func.max(PriceDaily.date)))


def load_bars(db: Session, instrument_id: int, since: date | None = None) -> pd.DataFrame:
    """Daily bars as stored: already adjusted for splits and bonuses by Groww's candle-data feed."""
    stmt = select(PriceDaily.date, PriceDaily.open, PriceDaily.high, PriceDaily.low, PriceDaily.close, PriceDaily.volume).where(
        PriceDaily.instrument_id == instrument_id
    )
    if since:
        stmt = stmt.where(PriceDaily.date >= since)
    rows = db.execute(stmt.order_by(PriceDaily.date)).all()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")
