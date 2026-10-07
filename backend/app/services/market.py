"""Market snapshot for the ticker and dashboard widgets: indices, sectors, breadth and every stock in the trading universe.

Information, not advice: "leaders" and "gainers" describe what already happened. During market hours (Mon–Fri 9:15–3:30
IST) prices come from Groww's live quotes, refreshed at most once a minute; otherwise the last close is shown.
"""

import threading
import time as _time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import IndexDaily, Instrument, PriceDaily
from app.engines import holidays
from app.rules import load_rules
from app.services import groww_service

IST = ZoneInfo("Asia/Kolkata")
INDEX_WIDGETS = [  # the index cards on the dashboard
    ("NIFTY", "Nifty 50"),
    ("SENSEX", "Sensex"),
    ("BANKNIFTY", "Nifty Bank"),
    ("NIFTYJR", "Nifty Next 50"),
    ("NIFTYMIDCAP", "Midcap 100"),
    ("NIFTYSMALL", "Smallcap 100"),
    ("NIFTYIT", "Nifty IT"),
    ("INDIAVIX", "India VIX"),
]
TICKER_NSE = ["NIFTY", "BANKNIFTY", "NIFTYJR", "NIFTYMIDCAP", "NIFTYSMALL", "FINNIFTY", "NIFTYIT", "INDIAVIX"]
TICKER_BSE = [("SENSEX", "Sensex"), ("BANKEX", "Bankex"), ("BSE100", "BSE 100")]
BSE_INDICES = {s for s, _ in TICKER_BSE}
SECTORS = [
    ("BANKNIFTY", "Banks"),
    ("NIFTYPVTBANK", "Private banks"),
    ("NIFTYPSUBANK", "PSU banks"),
    ("FINNIFTY", "Financials"),
    ("NIFTYIT", "IT"),
    ("NIFTYAUTO", "Auto"),
    ("NIFTYPHARMA", "Pharma"),
    ("NIFTYFMCG", "FMCG"),
    ("NIFTYMETAL", "Metals"),
    ("NIFTYREALTY", "Realty"),
    ("NIFTYMEDIA", "Media"),
    ("NIFTYCDTY", "Commodities"),
]
ALL_INDICES = {s for s, _ in INDEX_WIDGETS} | {s for s, _ in SECTORS} | set(TICKER_NSE) | BSE_INDICES
LIVE_TTL = 60  # seconds between live-quote refreshes
QUIET_TTL = 600  # outside market hours the snapshot is rebuilt at most every 10 minutes
TICKER_STOCKS = 40  # NSE tape: the most-traded stocks
BSE_PREFIX = "BSE:"  # BSE closes of the largest stocks are kept in index_daily as "BSE:RELIANCE" (see stock_data)

_lock = threading.Lock()
_live: dict = {"at": -1e9, "prices": {}}
_cache: dict = {"at": -1e9, "key": None, "data": None}


def market_open(now: datetime | None = None) -> bool:
    """Regular trading hours on a trading day (weekends and listed exchange holidays are shut)."""
    now = now or datetime.now(IST)
    return holidays.is_trading_day(now.date()) and holidays.OPEN <= now.time() <= holidays.CLOSE


def index_key(sym: str) -> str:
    return ("BSE_" if sym in BSE_INDICES else "NSE_") + sym


def _live_prices(db: Session, keys: list[str]) -> dict[str, float]:
    """Groww live quotes keyed exchange-first ("NSE_RELIANCE", "BSE_RELIANCE", "BSE_SENSEX"), or {} outside market
    hours or if Groww can't be reached. The same company trades at slightly different prices on NSE and BSE."""
    if not market_open():
        return {}
    with _lock:
        if _time.monotonic() - _live["at"] < LIVE_TTL:
            return _live["prices"]
        try:
            prices = groww_service.client(db).ltp(keys)
        except Exception:  # noqa: BLE001 — the last close is shown instead
            prices = {}
        _live.update(at=_time.monotonic(), prices=prices)
        return prices


def _ret(closes: np.ndarray, n: int) -> float | None:
    return round(float(closes[-1] / closes[-1 - n] - 1), 4) if len(closes) > n and closes[-1 - n] > 0 else None


def _series_stats(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, last_day: date, live: float | None, today: date, spark: int) -> dict:
    """Common numbers for an index or a stock. A live price extends the series when today's close isn't stored yet."""
    if live and last_day < today:
        last, prev = float(live), float(closes[-1])
        closes, highs, lows = np.append(closes, live), np.append(highs, live), np.append(lows, live)
    else:
        last, prev = float(closes[-1]), float(closes[-2])
    sma50 = float(closes[-50:].mean()) if len(closes) >= 50 else None
    sma200 = float(closes[-200:].mean()) if len(closes) >= 200 else None
    high52, low52 = float(highs[-250:].max()), float(lows[-250:].min())
    if sma50 and sma200:
        trend = "Uptrend" if last > sma50 > sma200 else "Downtrend" if last < sma50 < sma200 else "Sideways"
    else:
        trend = "New"
    return {
        "last": round(last, 2),
        "prev": round(prev, 2),
        "change": round(last - prev, 2),
        "change_pct": round(last / prev - 1, 4) if prev else 0.0,
        "spark": [round(float(x), 2) for x in closes[-spark:]],
        "ret_1w": _ret(closes, 5),
        "ret_1m": _ret(closes, 21),
        "ret_3m": _ret(closes, 63),
        "ret_1y": _ret(closes, 250),
        "above_50": bool(sma50 and last > sma50),
        "above_200": bool(sma200 and last > sma200),
        "high_52w": round(high52, 2),
        "low_52w": round(low52, 2),
        "from_high": round(last / high52 - 1, 4) if high52 else None,
        "trend": trend,
    }


def _nice_name(name: str | None, symbol: str) -> str:
    if not name:
        return symbol
    return " ".join(w if (w.isupper() and len(w) <= 3 and w not in {"LTD", "THE", "AND"}) else w.capitalize() for w in name.replace(".", ". ").split()).replace(". ", ".").strip()


def _indices(db: Session, live: dict[str, float], today: date) -> dict[str, dict]:
    since = today - timedelta(days=420)
    symbols = sorted(ALL_INDICES)
    rows = db.execute(
        select(IndexDaily.symbol, IndexDaily.date, IndexDaily.high, IndexDaily.low, IndexDaily.close)
        .where(IndexDaily.symbol.in_(symbols), IndexDaily.date >= since)
        .order_by(IndexDaily.symbol, IndexDaily.date)
    ).all()
    out: dict[str, dict] = {}
    df = pd.DataFrame(rows, columns=["symbol", "date", "high", "low", "close"])
    for sym, g in df.groupby("symbol"):
        if len(g) < 3:
            continue
        stats = _series_stats(g["close"].to_numpy(float), g["high"].to_numpy(float), g["low"].to_numpy(float), g["date"].iloc[-1], live.get(index_key(sym)), today, 60)
        out[sym] = stats | {"symbol": sym, "exchange": "BSE" if sym in BSE_INDICES else "NSE", "as_of": g["date"].iloc[-1].isoformat()}
    return out


def _bse_stocks(db: Session, live: dict[str, float], today: date) -> list[dict]:
    """The largest stocks at their BSE prices, for the BSE tape (ordered by NSE universe rank)."""
    rows = db.execute(
        select(IndexDaily.symbol, IndexDaily.date, IndexDaily.high, IndexDaily.low, IndexDaily.close)
        .where(IndexDaily.symbol.like(BSE_PREFIX + "%"), IndexDaily.date >= today - timedelta(days=30))
        .order_by(IndexDaily.symbol, IndexDaily.date)
    ).all()
    ranks = dict(db.execute(select(Instrument.symbol, Instrument.universe_rank).where(Instrument.in_universe.is_(True))).all())
    out = []
    for key, g in pd.DataFrame(rows, columns=["symbol", "date", "high", "low", "close"]).groupby("symbol"):
        sym = key[len(BSE_PREFIX):]
        if len(g) < 2 or sym not in ranks:
            continue
        stats = _series_stats(g["close"].to_numpy(float), g["high"].to_numpy(float), g["low"].to_numpy(float), g["date"].iloc[-1], live.get("BSE_" + sym), today, 10)
        out.append({"symbol": sym, "last": stats["last"], "change_pct": stats["change_pct"], "rank": ranks[sym] or 999})
    return sorted(out, key=lambda x: x["rank"])


def _stocks(db: Session, live: dict[str, float], today: date) -> list[dict]:
    insts = {i.id: i for i in db.scalars(select(Instrument).where(Instrument.in_universe.is_(True)))}
    if not insts:
        return []
    since = today - timedelta(days=420)
    rows = db.execute(
        select(PriceDaily.instrument_id, PriceDaily.date, PriceDaily.open, PriceDaily.high, PriceDaily.low, PriceDaily.close, PriceDaily.volume)
        .where(PriceDaily.instrument_id.in_(list(insts)), PriceDaily.date >= since)
        .order_by(PriceDaily.instrument_id, PriceDaily.date)
    ).all()
    df = pd.DataFrame(rows, columns=["iid", "date", "open", "high", "low", "close", "volume"])
    out = []
    for iid, g in df.groupby("iid"):
        if len(g) < 30:
            continue
        inst = insts[iid]
        c, v = g["close"].to_numpy(float), g["volume"].to_numpy(float)  # stored prices are already split-adjusted
        stats = _series_stats(c, g["high"].to_numpy(float), g["low"].to_numpy(float), g["date"].iloc[-1], live.get("NSE_" + inst.symbol), today, 30)
        out.append(
            stats
            | {
                "symbol": inst.symbol,
                "name": _nice_name(inst.name, inst.symbol),
                "rank": inst.universe_rank,
                "value_cr": round(float(c[-1] * v[-1]) / 1e7, 1),  # ₹ crore traded in the last full session
                "avg_value_cr": round(float((c[-20:] * v[-20:]).mean()) / 1e7, 1),
            }
        )
    return out


def _top(stocks: list[dict], key: str, n: int = 8, reverse: bool = True, keep=lambda s: True) -> list[str]:
    pool = [s for s in stocks if keep(s) and s.get(key) is not None]
    return [s["symbol"] for s in sorted(pool, key=lambda s: s[key], reverse=reverse)[:n]]


def snapshot(db: Session) -> dict:
    today = datetime.now(IST).date()
    latest = db.scalar(select(func.max(PriceDaily.date)))
    is_live = market_open()
    key = (latest, is_live)
    with _lock:
        fresh = _time.monotonic() - _cache["at"] < (LIVE_TTL if is_live else QUIET_TTL)
        if _cache["data"] is not None and _cache["key"] == key and fresh:
            return _cache["data"]
    universe = db.scalars(select(Instrument.symbol).where(Instrument.in_universe.is_(True))).all()
    bse_syms = [k[len(BSE_PREFIX):] for k in db.scalars(select(IndexDaily.symbol).where(IndexDaily.symbol.like(BSE_PREFIX + "%")).distinct())]
    keys = [index_key(s) for s in sorted(ALL_INDICES)] + ["NSE_" + s for s in universe] + ["BSE_" + s for s in bse_syms]
    live = _live_prices(db, keys) if is_live else {}
    indices = _indices(db, live, today)
    stocks = _stocks(db, live, today)
    bse_stocks = _bse_stocks(db, live, today)
    n = len(stocks) or 1
    breadth = {
        "total": len(stocks),
        "advancers": sum(1 for s in stocks if s["change_pct"] > 0.0005),
        "decliners": sum(1 for s in stocks if s["change_pct"] < -0.0005),
        "above_50": round(sum(s["above_50"] for s in stocks) / n, 3),
        "above_200": round(sum(s["above_200"] for s in stocks) / n, 3),
        "near_high": sum(1 for s in stocks if s["from_high"] is not None and s["from_high"] >= -0.01),
        "near_low": sum(1 for s in stocks if s["last"] <= s["low_52w"] * 1.01),
    }
    breadth["unchanged"] = breadth["total"] - breadth["advancers"] - breadth["decliners"]
    # the sector page behind each tile (and behind the Nifty Bank / Nifty IT cards)
    sector_keys = {s["index"]: key for key, s in load_rules("sectors")["sectors"].items() if s.get("index")}
    data = {
        "as_of": latest.isoformat() if latest else None,
        "live": bool(live),
        "market_open": is_live,
        "updated_at": datetime.now(IST).isoformat(timespec="seconds"),
        "indices": [indices[s] | {"label": label, "sector": sector_keys.get(s)} for s, label in INDEX_WIDGETS if s in indices],
        "_all_indices": indices,
        "_bse_stocks": bse_stocks,
        "sectors": [indices[s] | {"label": label, "key": sector_keys.get(s)} for s, label in SECTORS if s in indices],
        "breadth": breadth,
        "stocks": {s["symbol"]: s for s in stocks},
        "lists": {
            "leaders": _top(stocks, "ret_3m", keep=lambda s: s["trend"] == "Uptrend" and (s["from_high"] or -1) >= -0.10),
            "gainers": _top(stocks, "change_pct"),
            "losers": _top(stocks, "change_pct", reverse=False),
            "active": _top(stocks, "value_cr"),
            "highs": _top(stocks, "from_high", keep=lambda s: (s["from_high"] or -1) >= -0.03),
        },
    }
    with _lock:
        _cache.update(at=_time.monotonic(), key=key, data=data)
    return data


NSE_LABELS = dict(INDEX_WIDGETS) | {"FINNIFTY": "Fin Nifty"}


def _tick(i: dict, label: str, kind: str) -> dict:
    return {"symbol": i["symbol"], "label": label, "last": i["last"], "change_pct": i["change_pct"], "kind": kind}


def ticker(db: Session) -> dict:
    """Two tapes, like a TV strip: NSE (its indices, then the most-traded stocks at NSE prices) and BSE (its indices,
    then the largest stocks at BSE prices)."""
    snap = snapshot(db)
    every = snap["_all_indices"]
    nse = [_tick(every[s], NSE_LABELS.get(s, s), "index") for s in TICKER_NSE if s in every]
    stocks = sorted(snap["stocks"].values(), key=lambda s: -(s["avg_value_cr"] or 0))[:TICKER_STOCKS]
    nse += [_tick(s, s["symbol"], "stock") for s in stocks]
    bse = [_tick(every[s], label, "index") for s, label in TICKER_BSE if s in every]
    bse += [_tick(s, s["symbol"], "stock") for s in snap["_bse_stocks"]]
    return {"live": snap["live"], "market_open": snap["market_open"], "as_of": snap["as_of"], "updated_at": snap["updated_at"], "nse": nse, "bse": bse}


def reset_cache() -> None:
    """For tests."""
    with _lock:
        _cache.update(at=-1e9, key=None, data=None)
        _live.update(at=-1e9, prices={})
