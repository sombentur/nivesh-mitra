"""Background jobs, on Indian time, inside the backend process.

The PC may be off at the scheduled time, so on every start-up the app checks what was missed and runs it
("catch-up"). Every job is idempotent, so running one twice is harmless. Each run is recorded in job_runs.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_config
from app.db.base import SessionLocal, utcnow
from app.db.migrate import backup_database
from app.db.models import Instrument, JobRun
from app.services import intraday_data, intraday_practice, intraday_trading, market, mf_data, mf_scores, news, stock_data, trading
from app.services.errors import JobSkipped

log = logging.getLogger("niveshmitra.jobs")
IST = ZoneInfo("Asia/Kolkata")


@dataclass
class JobSpec:
    name: str
    label: str
    fn: Callable[[Session, mf_data.Progress], str]
    triggers: list[CronTrigger]
    then: list[str] = field(default_factory=list)  # jobs to run after this one succeeds
    then_always: list[str] = field(default_factory=list)  # …and jobs to run after it whatever happened
    stale_after: timedelta | None = None  # catch-up runs it at start-up if the last success is older
    skip_if_fresh: timedelta | None = None  # automatic runs are skipped if it succeeded this recently ("Run now" always runs)


def _backup(_db: Session, _progress: mf_data.Progress) -> str:
    target = backup_database("nightly")
    return f"saved {target.name}" if target else "nothing to back up yet"


JOBS: dict[str, JobSpec] = {
    j.name: j
    for j in [
        JobSpec(
            "amfi_scheme_master",
            "Fund list (AMFI scheme master)",
            mf_data.sync_scheme_master,
            [CronTrigger(day_of_week="sun", hour=9, minute=0, timezone=IST)],
            then=["amfi_nav_daily"],
            stale_after=timedelta(days=7),
        ),
        JobSpec(
            "amfi_nav_daily",
            "Daily NAVs (AMFI)",
            mf_data.update_daily_navs,
            # AMFI publishes by 11 pm; fund-of-funds by 10 am next day. Re-running is harmless.
            [CronTrigger(hour=h, minute=m, timezone=IST) for h, m in [(22, 0), (23, 30), (7, 5), (10, 30)]],
            then=["mf_history_backfill"],
            stale_after=timedelta(hours=12),
        ),
        JobSpec(
            "mf_history_backfill",
            "Fund history download (mfapi.in)",
            mf_data.backfill_history,
            [],
            then=["mf_scoring"],
        ),
        JobSpec(
            "amfi_ter",
            "Fund expense ratios (AMFI)",
            mf_scores.sync_ter,
            [CronTrigger(day_of_week="sun", hour=10, minute=0, timezone=IST)],
            then=["mf_scoring"],
            stale_after=timedelta(days=8),
        ),
        JobSpec(
            "mf_scoring",
            "Fund scores within each category",
            mf_scores.run_scoring,
            [CronTrigger(day_of_week="sat", hour=7, minute=30, timezone=IST)],
            stale_after=timedelta(days=8),
            skip_if_fresh=timedelta(days=6),
        ),
        JobSpec(
            "db_backup",
            "Nightly database backup",
            _backup,
            [CronTrigger(hour=2, minute=30, timezone=IST)],
            stale_after=timedelta(hours=36),
        ),
        # ---- stocks & practice trading (needs Groww market data, except the instrument list) ----
        JobSpec(
            "groww_instruments",
            "Stock list (Groww, public)",
            stock_data.sync_instruments,
            [CronTrigger(day_of_week="sun", hour=8, minute=30, timezone=IST)],
            then=["stock_universe"],
            stale_after=timedelta(days=8),
        ),
        JobSpec(
            "stock_universe",
            "Trading universe: most-traded stocks (Groww)",
            stock_data.scan_universe,
            [],
            then=["stock_backfill"],
            skip_if_fresh=timedelta(days=25),
        ),
        JobSpec("stock_backfill", "Stock price history since 2020 (Groww)", stock_data.backfill_prices, [], then=["stock_intraday"]),
        JobSpec(
            "stock_intraday",
            "15-minute price history + repair of daily opens (Groww)",
            intraday_data.sync_intraday,
            [],
            then_always=["trading_after_close"],  # ideas are still made if this step fails
        ),
        JobSpec(
            "stock_prices_daily",
            "Daily stock prices (Groww)",
            stock_data.update_daily_prices,
            [CronTrigger(day_of_week="mon-fri", hour=h, minute=m, timezone=IST) for h, m in [(16, 45), (19, 0)]],
            then=["stock_intraday"],  # at start-up it runs whenever a finished session is missing (see catch_up)
        ),
        JobSpec("trading_after_close", "Practice trades + tomorrow's ideas", trading.after_close, [], then_always=["intraday_practice"]),
        JobSpec("intraday_practice", "Intraday practice: next session's plan + last session's scoreboard", intraday_practice.after_close, []),
        JobSpec(
            "news_pulse",
            "News pulse: headlines for the market heavyweights and movers (Trendlyne + Claude)",
            news.refresh,
            [CronTrigger(day_of_week="mon-fri", hour=h, minute=m, timezone=IST) for h, m in [(8, 40), (15, 45)]],
        ),
        JobSpec(
            "intraday_backtests",
            "Test the same-day (intraday) setups on 15-minute history",
            intraday_trading.run_intraday_backtests,
            [CronTrigger(day_of_week="sat", hour=11, minute=30, timezone=IST)],
            then=["intraday_practice"],  # the plan quotes each setup's latest test result
            skip_if_fresh=timedelta(days=5),
        ),
        JobSpec(
            "stock_backtests",
            "Backtest the trading setups (5+ years, with costs)",
            trading.run_backtests,
            [CronTrigger(day_of_week="sat", hour=11, minute=0, timezone=IST)],
            then=["trading_after_close"],  # the first backtest unlocks ideas straight away
            skip_if_fresh=timedelta(days=5),
        ),
    ]
}

PRICE_JOBS = ("stock_prices_daily", "stock_backfill", "stock_universe")
_locks = {name: threading.Lock() for name in JOBS}
_progress: dict[str, dict] = {}
_scheduler: BackgroundScheduler | None = None


def is_running(name: str) -> bool:
    return _locks[name].locked()


def progress(name: str) -> dict | None:
    return _progress.get(name)


def next_run(name: str):
    if _scheduler is None:
        return None
    times = [j.next_run_time for j in _scheduler.get_jobs() if j.id.startswith(f"{name}#") and j.next_run_time]
    return min(times) if times else None


def run_job(name: str, trigger: str = "manual") -> bool:
    """Run a job now in this thread. Returns False if it was already running."""
    spec = JOBS[name]
    if not _locks[name].acquire(blocking=False):
        return False
    ok = False
    try:
        with SessionLocal() as db:
            run = JobRun(job_name=name, status="running", started_at=utcnow(), detail=f"started by {trigger}")
            db.add(run)
            db.commit()
            run_id = run.id

            def report(done: int, total: int) -> None:
                _progress[name] = {"done": done, "total": total}

            recent = last_success(db, name) if spec.skip_if_fresh and not trigger.startswith("manual") else None
            if recent and recent.started_at > utcnow() - spec.skip_if_fresh:
                detail, status = f"skipped — last done {recent.started_at:%d %b}; runs again after {spec.skip_if_fresh.days} days", "skipped"
            else:
                detail, status = None, None
            try:
                if status is None:
                    detail = spec.fn(db, report)
                    status = "ok"
            except JobSkipped as exc:
                db.rollback()
                detail, status = str(exc), "skipped"
            except Exception as exc:  # noqa: BLE001 — record any failure, never crash the app
                db.rollback()
                log.exception("job %s failed", name)
                detail, status = f"{type(exc).__name__}: {exc}"[:1000], "failed"
            run = db.get(JobRun, run_id)
            run.status, run.detail, run.finished_at = status, detail, utcnow()
            db.commit()
            ok = status == "ok"
    finally:
        _progress.pop(name, None)
        _locks[name].release()
    if ok and name in PRICE_JOBS:
        market.reset_cache()  # the ticker and widgets show the new prices straight away
    for nxt in (spec.then if ok else []) + spec.then_always:
        run_job_async(nxt, f"after {name}")
    return True


def run_job_async(name: str, trigger: str = "manual") -> bool:
    if is_running(name):
        return False
    threading.Thread(target=run_job, args=(name, trigger), daemon=True, name=f"job-{name}").start()
    return True


def last_success(db: Session, name: str) -> JobRun | None:
    return db.scalar(select(JobRun).where(JobRun.job_name == name, JobRun.status == "ok").order_by(JobRun.id.desc()))


def last_run(db: Session, name: str) -> JobRun | None:
    return db.scalar(select(JobRun).where(JobRun.job_name == name).order_by(JobRun.id.desc()))


def catch_up() -> None:
    """Run whatever was missed while the PC was off. Chained jobs follow automatically."""
    with SessionLocal() as db:
        # A job that was "running" when the PC shut down never finished.
        for stuck in db.scalars(select(JobRun).where(JobRun.status == "running")):
            stuck.status, stuck.detail, stuck.finished_at = "failed", "interrupted (app was closed)", utcnow()
        db.commit()
        now = utcnow()

        def stale(name: str) -> bool:
            last, limit = last_success(db, name), JOBS[name].stale_after
            return last is None or (limit is not None and last.started_at < now - limit)

        chain = next((n for n in ("amfi_scheme_master", "amfi_nav_daily") if stale(n)), None)
        if chain is None and mf_data.pending_history(db):
            chain = "mf_history_backfill"
        if chain is None:
            chain = "amfi_ter" if stale("amfi_ter") else ("mf_scoring" if stale("mf_scoring") else None)
        backup_due = stale("db_backup")
        stock_chain = "groww_instruments" if stale("groww_instruments") else None
        if stock_chain is None and not db.scalar(select(Instrument.id).where(Instrument.in_universe.is_(True)).limit(1)):
            stock_chain = "stock_universe"
        if stock_chain is None and stock_data.universe_missing_history(db):
            stock_chain = "stock_backfill"  # e.g. the PC was closed during the first history download
        if stock_chain is None and intraday_data.missing_intraday(db):
            stock_chain = "stock_intraday"
        if stock_chain is None and last_success(db, "stock_backtests") is None:
            stock_chain = "stock_backtests"
        if stock_chain is None and last_success(db, "intraday_backtests") is None:
            stock_chain = "intraday_backtests"
        prices_due = stock_data.prices_behind(db)  # a finished session isn't in yet (holidays and weekends skipped)
        plan_due = not prices_due and stock_chain is None and intraday_practice.plan_missing(db)
    if backup_due:
        run_job("db_backup", "catch-up at start-up")  # before downloading anything new
    if chain:
        run_job(chain, "catch-up at start-up")
    if stock_chain:
        run_job(stock_chain, "catch-up at start-up")
    if prices_due:
        run_job("stock_prices_daily", "catch-up at start-up")
    elif plan_due:
        run_job("intraday_practice", "catch-up at start-up")


def start() -> None:
    global _scheduler
    if not get_config().scheduler_enabled or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=IST)
    for spec in JOBS.values():
        for i, trig in enumerate(spec.triggers):
            _scheduler.add_job(
                run_job, trig, args=[spec.name, "schedule"], id=f"{spec.name}#{i}", misfire_grace_time=3600, coalesce=True
            )
    _scheduler.start()
    threading.Thread(target=catch_up, daemon=True, name="catch-up").start()


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
