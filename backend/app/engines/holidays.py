"""Trading days: weekends, exchange holidays and special sessions (rules/market_holidays.yaml). Pure functions."""

from datetime import date, time, timedelta
from functools import lru_cache

from app.rules import load_rules

OPEN, CLOSE = time(9, 15), time(15, 30)


def _day(key) -> date:
    return key if isinstance(key, date) else date.fromisoformat(str(key))


@lru_cache
def _tables() -> tuple[dict[date, str], dict[date, str], dict[date, dict]]:
    r = load_rules("market_holidays")
    holidays = {_day(k): v for k, v in (r.get("holidays") or {}).items()}
    weekend = {_day(k): v for k, v in (r.get("weekend_holidays") or {}).items()}
    special = {_day(k): v for k, v in (r.get("special_sessions") or {}).items()}
    return holidays, weekend, special


def holiday_name(d: date) -> str | None:
    """The holiday's name if the market is shut for one that day (weekday holidays and named weekend festivals)."""
    holidays, weekend, _ = _tables()
    return holidays.get(d) or weekend.get(d)


def special_session(d: date) -> dict | None:
    """{"name", "full_day", "note"?} when the exchanges trade on a day that is normally closed."""
    return _tables()[2].get(d)


def is_trading_day(d: date) -> bool:
    """A normal 9:15–3:30 session is expected: a weekday that isn't a listed holiday, or a full-day special session."""
    special = special_session(d)
    if special:
        return bool(special.get("full_day"))
    return d.weekday() < 5 and d not in _tables()[0]


def next_trading_day(d: date) -> date:
    """The first trading day strictly after `d`."""
    n = d + timedelta(days=1)
    while not is_trading_day(n):
        n += timedelta(days=1)
    return n


def known_until() -> date | None:
    """The holiday list covers up to the end of the last year it mentions; later weekdays are assumed to be trading days."""
    years = [d.year for d in _tables()[0]]
    return date(max(years), 12, 31) if years else None


def prev_trading_day(d: date) -> date:
    """The last trading day strictly before `d`."""
    p = d - timedelta(days=1)
    while not is_trading_day(p):
        p -= timedelta(days=1)
    return p


FINAL = time(15, 40)  # a session's prices are final a few minutes after the 3:30 PM close


def last_completed_session(now) -> date:
    """The newest session whose prices are final: today from 3:40 PM on a trading day, otherwise the trading day before."""
    today = now.date()
    if is_trading_day(today) and now.time() >= FINAL:
        return today
    return prev_trading_day(today)


def closed_reason(d: date) -> str | None:
    """Why there is no normal session on `d`: the holiday's name, or "Weekend". None on a trading day."""
    if is_trading_day(d):
        return None
    return holiday_name(d) or ("Weekend" if d.weekday() >= 5 else "Market holiday")
