"""The trading calendar: which days the market is open, how it moved on days gone by, and your own dates.

Past days come from the prices that actually traded (a weekday with no Nifty 50 candle was a holiday, a weekend day with
one was a special session). Today and the days ahead come from the holiday list in rules/market_holidays.yaml.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import IndexDaily, PaperAccount, PaperTrade, Recommendation, User
from app.engines import holidays
from app.services import profile as profile_svc
from app.services.stock_data import latest_session, now_ist

MAX_DAYS = 62
INDICES = {"NIFTY": "nifty", "SENSEX": "sensex"}


def _moves(db: Session, start: date, end: date) -> dict[str, dict[date, dict]]:
    """Per index: {session date: {"close", "change_pct"}} (change from the previous session that traded)."""
    rows = db.execute(
        select(IndexDaily.symbol, IndexDaily.date, IndexDaily.close)
        .where(IndexDaily.symbol.in_(list(INDICES)), IndexDaily.date >= start - timedelta(days=15), IndexDaily.date <= end)
        .order_by(IndexDaily.symbol, IndexDaily.date)
    ).all()
    out: dict[str, dict[date, dict]] = {v: {} for v in INDICES.values()}
    prev: dict[str, float] = {}
    for sym, day, close in rows:
        if sym in prev and prev[sym]:
            out[INDICES[sym]][day] = {"close": round(close, 2), "change_pct": round(close / prev[sym] - 1, 4)}
        prev[sym] = close
    return out


def _practice(db: Session, start: date, end: date) -> tuple[dict[date, tuple[float, int]], dict[date, int]]:
    """Practice account: profit/loss and count of trades closed each day; practice ideas made for each session."""
    pnl: dict[date, tuple[float, int]] = {}
    account_id = db.scalar(select(PaperAccount.id).order_by(PaperAccount.id.desc()).limit(1))
    if account_id is not None:
        rows = db.execute(
            select(PaperTrade.exit_date, func.sum(PaperTrade.net_pnl), func.count())
            .where(PaperTrade.account_id == account_id, PaperTrade.status == "closed", PaperTrade.exit_date.between(start, end))
            .group_by(PaperTrade.exit_date)
        ).all()
        pnl = {d: (round(p or 0.0, 2), n) for d, p, n in rows}
    ideas = dict(
        db.execute(
            select(Recommendation.for_session, func.count())
            .where(Recommendation.engine == "swing", Recommendation.for_session.between(start, end))
            .group_by(Recommendation.for_session)
        ).all()
    )
    return pnl, ideas


def _events(db: Session, user: User) -> dict[date, list[str]]:
    out: dict[date, list[str]] = {}
    paper = profile_svc.paper_status(db)
    if paper["ends_on"]:
        out.setdefault(date.fromisoformat(paper["ends_on"]), []).append("Practice period ends: your practice report is ready")
    profile = profile_svc.current_profile(db, user)
    if profile and profile.review_due_on:
        out.setdefault(profile.review_due_on, []).append("Risk profile review due")
    return out


def market_state(now: datetime) -> dict:
    """Is the market open right now, and when does it open next?"""
    today = now.date()
    if holidays.is_trading_day(today):
        if now.time() < holidays.OPEN:
            return {"state": "pre", "next_open": today.isoformat()}
        if now.time() <= holidays.CLOSE:
            return {"state": "open", "next_open": today.isoformat()}
    return {"state": "closed", "next_open": holidays.next_trading_day(today).isoformat()}


def build(db: Session, user: User, start: date, end: date) -> dict:
    now = now_ist()
    today = now.date()
    latest = latest_session(db)
    moves = _moves(db, start, end)
    pnl, ideas = _practice(db, start, end)
    events = _events(db, user)
    days = []
    d = start
    while d <= end:
        nifty = moves["nifty"].get(d)
        special = holidays.special_session(d)
        if latest and d <= latest:  # what actually happened
            traded = nifty is not None or d in moves["sensex"]
            if traded:
                status = "special" if d.weekday() >= 5 else "trading"
                name = (special or {}).get("name") or ("Special trading session" if status == "special" else None)
            else:
                status = "weekend" if d.weekday() >= 5 else "holiday"
                name = holidays.holiday_name(d) or ("Market holiday" if status == "holiday" else None)
        elif special and not special.get("full_day"):
            status, name = "special", special["name"]
        elif holidays.is_trading_day(d):
            status, name = ("special" if d.weekday() >= 5 else "trading"), (special or {}).get("name")
        else:
            status = "weekend" if d.weekday() >= 5 else "holiday"
            name = holidays.holiday_name(d)
        closed = pnl.get(d)
        days.append(
            {
                "date": d.isoformat(),
                "status": status,
                "name": name,
                "note": (special or {}).get("note") if status == "special" else None,
                "nifty": nifty,
                "sensex": moves["sensex"].get(d),
                "pnl": closed[0] if closed else None,
                "closed_trades": closed[1] if closed else 0,
                "ideas": ideas.get(d, 0),
                "events": events.get(d, []),
            }
        )
        d += timedelta(days=1)
    known = holidays.known_until()
    return {
        "today": today.isoformat(),
        "latest_session": latest.isoformat() if latest else None,
        "market": market_state(now),
        "holidays_known_until": known.isoformat() if known else None,
        "days": days,
    }
