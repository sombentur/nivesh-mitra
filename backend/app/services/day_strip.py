"""The Yesterday / Today / Tomorrow row: the last trading day, today, and the next trading day.

"Yesterday" and "tomorrow" skip weekends and exchange holidays, and each card says which days were skipped and why.
"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Instrument, PriceDaily
from app.engines import holidays
from app.services import intraday_practice, market_calendar
from app.services.stock_data import latest_session, now_ist

MOVERS = 3


def _skipped(after: date, before: date) -> list[dict]:
    """The non-trading days strictly between two dates, with the reason for each."""
    out, d = [], after + timedelta(days=1)
    while d < before:
        out.append({"date": d.isoformat(), "reason": holidays.closed_reason(d) or "Market closed"})
        d += timedelta(days=1)
    return out


def day_market(db: Session, day: date) -> dict | None:
    """How the market did on one session: index moves, how many of the tracked stocks rose or fell, and the biggest movers."""
    moves = market_calendar._moves(db, day, day)
    nifty = moves["nifty"].get(day)
    if nifty is None:
        return None
    prev = func.lag(PriceDaily.close).over(partition_by=PriceDaily.instrument_id, order_by=PriceDaily.date)
    inner = (
        select(PriceDaily.instrument_id, PriceDaily.date, PriceDaily.close, prev.label("prev"))
        .join(Instrument, Instrument.id == PriceDaily.instrument_id)
        .where(Instrument.in_universe.is_(True), PriceDaily.date >= day - timedelta(days=12), PriceDaily.date <= day)
        .subquery()
    )
    rows = db.execute(
        select(Instrument.symbol, inner.c.close, inner.c.prev).join(Instrument, Instrument.id == inner.c.instrument_id).where(inner.c.date == day, inner.c.prev.is_not(None))
    ).all()
    changes = sorted(((sym, close, close / before - 1) for sym, close, before in rows if before), key=lambda x: x[2])
    view = lambda x: {"symbol": x[0], "last": round(x[1], 2), "change_pct": round(x[2], 4)}  # noqa: E731
    return {
        "nifty": nifty,
        "sensex": moves["sensex"].get(day),
        "advancers": sum(1 for c in changes if c[2] > 0.0005),
        "decliners": sum(1 for c in changes if c[2] < -0.0005),
        "stocks": len(changes),
        "gainers": [view(c) for c in reversed(changes[-MOVERS:])],
        "losers": [view(c) for c in changes[:MOVERS]],
    }


def build(db: Session) -> dict:
    now = now_ist()
    today = now.date()
    previous, upcoming = holidays.prev_trading_day(today), holidays.next_trading_day(today)
    latest = latest_session(db)
    plans, recaps = intraday_practice.stored(db)
    trading_today = holidays.is_trading_day(today)
    special = holidays.special_session(today)
    return {
        "previous": {
            "date": previous.isoformat(),
            "is_yesterday": previous == today - timedelta(days=1),
            "skipped": _skipped(previous, today),
            "market": day_market(db, previous),
            "recap": recaps.get(previous.isoformat()),
        },
        "today": {
            "date": today.isoformat(),
            "status": "trading" if trading_today else ("special" if special else ("weekend" if today.weekday() >= 5 and not holidays.holiday_name(today) else "holiday")),
            "name": (special or {}).get("name") if special else holidays.holiday_name(today),
            "note": (special or {}).get("note"),
            "market": market_calendar.market_state(now),
            "result": day_market(db, today) if latest and latest >= today else None,  # in once today's prices are final
            "plan": plans.get(today.isoformat()) if trading_today else None,
            "recap": recaps.get(today.isoformat()),
        },
        "next": {
            "date": upcoming.isoformat(),
            "is_tomorrow": upcoming == today + timedelta(days=1),
            "skipped": _skipped(today, upcoming),
            "plan": plans.get(upcoming.isoformat()),
            # tomorrow's plan needs today's closing prices
            "waiting_for_close": trading_today and not (latest and latest >= today),
        },
        "latest_session": latest.isoformat() if latest else None,
    }
