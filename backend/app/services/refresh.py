"""The Refresh button: is the data current, and bring it up to date on request.

"Current" for prices means the last session that has finished (holidays and weekends skipped). During market hours the
live quotes cover today; a day's candles are stored once the market has closed.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import scheduler
from app.db.base import utcnow
from app.db.models import MfScheme
from app.engines import holidays
from app.services import intraday_practice, market, stock_data
from app.services.stock_data import latest_session, now_ist

PRICE_JOBS = ("stock_prices_daily", "stock_intraday", "trading_after_close", "intraday_practice", "stock_backfill")
NAV_JOB = "amfi_nav_daily"
NAV_RECHECK = timedelta(hours=3)


def _run_view(run) -> dict | None:
    return None if run is None else {"status": run.status, "at": (run.finished_at or run.started_at).isoformat(), "detail": run.detail}


def freshness(db: Session) -> dict:
    now = now_ist()
    latest = latest_session(db)
    last_ok, last_run = scheduler.last_success(db, "stock_prices_daily"), scheduler.last_run(db, "stock_prices_daily")
    failed = last_run is not None and last_run.status == "failed" and (last_ok is None or last_run.id > last_ok.id)
    nav_date = db.scalar(
        select(MfScheme.latest_nav_date)
        .where(MfScheme.is_active.is_(True), MfScheme.latest_nav_date.is_not(None))
        .group_by(MfScheme.latest_nav_date)
        .order_by(func.count().desc(), MfScheme.latest_nav_date.desc())
        .limit(1)
    )
    running = [
        {"name": name, "label": scheduler.JOBS[name].label, "progress": scheduler.progress(name)}
        for name in (*PRICE_JOBS, NAV_JOB, "news_pulse")
        if scheduler.is_running(name)
    ]
    return {
        "now": now.isoformat(timespec="seconds"),
        "market_open": market.market_open(now),
        "prices": {
            "latest_session": latest.isoformat() if latest else None,
            "expected_session": holidays.last_completed_session(now).isoformat(),
            "behind": stock_data.prices_behind(db),
            "updated_at": _run_view(last_ok)["at"] if last_ok else None,
            "error": last_run.detail if failed else None,
        },
        "navs": {"date": nav_date.isoformat() if nav_date else None},
        "running": running,
    }


def start(db: Session) -> dict:
    """Start whatever is needed to bring the data up to date. Live quotes are always re-read."""
    market.reset_cache()
    started = []
    if stock_data.prices_behind(db):
        if scheduler.run_job_async("stock_prices_daily", "refresh button"):
            started.append("stock_prices_daily")
    elif intraday_practice.plan_missing(db):
        if scheduler.run_job_async("intraday_practice", "refresh button"):
            started.append("intraday_practice")
    nav_ok = scheduler.last_success(db, NAV_JOB)
    if nav_ok is None or nav_ok.started_at < utcnow() - NAV_RECHECK:
        if scheduler.run_job_async(NAV_JOB, "refresh button"):
            started.append(NAV_JOB)
    return {"started": started, **freshness(db)}
