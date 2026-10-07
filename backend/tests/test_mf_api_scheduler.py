from datetime import date, timedelta

from app import scheduler
from app.db.base import SessionLocal
from app.db.models import Instrument, JobRun
from tests.conftest import CSRF
from tests.test_mf_data import _full_sync, sources  # noqa: F401 — fixture reuse


def test_mf_endpoints_need_login(client):
    assert client.get("/api/mf/search").status_code == 401
    assert client.get("/api/data/status").status_code == 401


def test_search_categories_and_fund_page(signed_in, sources):  # noqa: F811
    with SessionLocal() as db:
        _full_sync(db)
    cats = signed_in.get("/api/mf/categories").json()
    assert {"asset_class": "Equity", "category": "Flexi Cap Fund", "count": 1} in cats

    hits = signed_in.get("/api/mf/search", params={"q": "parag flexi"}).json()
    assert [h["scheme_code"] for h in hits] == [122639]  # regular plan hidden by default
    all_hits = signed_in.get("/api/mf/search", params={"q": "parag", "include_all": True}).json()
    assert {h["scheme_code"] for h in all_hits} == {122639, 122640}
    assert signed_in.get("/api/mf/search", params={"category": "ELSS"}).json()[0]["scheme_code"] == 120503

    page = signed_in.get("/api/mf/schemes/122639").json()
    assert page["history"]["status"] == "ready" and page["returns"]["5y"] is not None
    assert page["twin"]["scheme_code"] == 122640 and page["launch_date"] == "2013-05-24"
    assert 0 < len(page["chart"]) <= 700
    assert signed_in.get("/api/mf/schemes/999999").status_code == 404


def test_on_demand_history_for_untracked_fund(signed_in, sources):  # noqa: F811
    with SessionLocal() as db:
        _full_sync(db)
    assert signed_in.get("/api/mf/schemes/122640").json()["history"]["status"] == "not_downloaded"
    page = signed_in.post("/api/mf/schemes/122640/history", headers=CSRF).json()
    assert page["history"]["status"] == "ready"


def test_data_status(signed_in, sources):  # noqa: F811
    with SessionLocal() as db:
        _full_sync(db)
    st = signed_in.get("/api/data/status").json()
    assert st["nav"]["latest_nav_date"] == "2026-09-29"
    assert st["nav"]["tracked"] == 4 and st["nav"]["synced"] == 4
    assert {j["name"] for j in st["jobs"]} == set(scheduler.JOBS)


def test_run_job_records_success_failure_and_chains(monkeypatch, sources):  # noqa: F811
    chained = []
    monkeypatch.setattr(scheduler, "run_job_async", lambda name, trigger="manual": chained.append(name) or True)
    assert scheduler.run_job("amfi_scheme_master", "test") is True
    assert chained == ["amfi_nav_daily"]

    def boom(db, progress):
        raise RuntimeError("source exploded")

    monkeypatch.setitem(scheduler.JOBS, "amfi_nav_daily", scheduler.JobSpec("amfi_nav_daily", "x", boom, []))
    scheduler.run_job("amfi_nav_daily", "test")
    with SessionLocal() as db:
        runs = {r.job_name: r for r in db.query(JobRun).all()}
        assert runs["amfi_scheme_master"].status == "ok"
        assert runs["amfi_nav_daily"].status == "failed" and "source exploded" in runs["amfi_nav_daily"].detail


def test_jobs_waiting_on_prerequisites_are_skipped_not_failed(monkeypatch):
    chained = []
    monkeypatch.setattr(scheduler, "run_job_async", lambda name, trigger="manual": chained.append(name) or True)
    scheduler.run_job("stock_backfill", "manual by me")  # no trading universe yet
    scheduler.run_job("stock_backtests", "manual by me")  # no price history yet
    with SessionLocal() as db:
        runs = {r.job_name: r for r in db.query(JobRun).all()}
    assert runs["stock_backfill"].status == "skipped" and "Waiting for the stock ranking" in runs["stock_backfill"].detail
    assert runs["stock_backtests"].status == "skipped"
    assert chained == []  # nothing runs after a skipped job


def test_job_cannot_run_twice_at_once(monkeypatch):
    lock = scheduler._locks["mf_history_backfill"]
    lock.acquire()
    try:
        assert scheduler.run_job("mf_history_backfill") is False
        assert scheduler.run_job_async("mf_history_backfill") is False
    finally:
        lock.release()


def test_catch_up_runs_master_first_then_marks_interrupted(monkeypatch):
    ran = []
    monkeypatch.setattr(scheduler, "run_job", lambda name, trigger="manual": ran.append(name) or True)
    with SessionLocal() as db:
        db.add(JobRun(job_name="mf_history_backfill", status="running"))
        db.commit()
    scheduler.catch_up()
    assert ran == ["db_backup", "amfi_scheme_master", "groww_instruments", "stock_prices_daily"]
    with SessionLocal() as db:
        assert db.query(JobRun).filter_by(status="running").count() == 0


def test_catch_up_skips_fresh_jobs(monkeypatch):
    ran = []
    monkeypatch.setattr(scheduler, "run_job", lambda name, trigger="manual": ran.append(name) or True)
    monkeypatch.setattr(scheduler.intraday_data, "missing_intraday", lambda db: 0)
    monkeypatch.setattr(scheduler.stock_data, "prices_behind", lambda db: False)
    monkeypatch.setattr(scheduler.intraday_practice, "plan_missing", lambda db: False)
    with SessionLocal() as db:
        for name in ("amfi_scheme_master", "amfi_nav_daily", "db_backup", "groww_instruments", "stock_prices_daily", "amfi_ter", "mf_scoring", "stock_backtests", "intraday_backtests"):
            db.add(JobRun(job_name=name, status="ok"))
        db.add(Instrument(symbol="X", groww_symbol="NSE-X", in_universe=True, history_start=date(2020, 1, 1), history_complete=True))
        db.commit()
    scheduler.catch_up()
    assert ran == []


def test_catch_up_resumes_the_stock_pipeline(monkeypatch):
    """Closed during the first history download → download resumes; history there but never backtested → backtests."""
    ran = []
    monkeypatch.setattr(scheduler, "run_job", lambda name, trigger="manual": ran.append(name) or True)
    monkeypatch.setattr(scheduler.intraday_data, "missing_intraday", lambda db: 0)
    monkeypatch.setattr(scheduler.stock_data, "prices_behind", lambda db: False)
    monkeypatch.setattr(scheduler.intraday_practice, "plan_missing", lambda db: False)
    with SessionLocal() as db:
        for name in ("amfi_scheme_master", "amfi_nav_daily", "db_backup", "groww_instruments", "stock_prices_daily", "amfi_ter", "mf_scoring"):
            db.add(JobRun(job_name=name, status="ok"))
        inst = Instrument(symbol="X", groww_symbol="NSE-X", in_universe=True, history_start=date(2026, 6, 1))
        db.add(inst)
        db.commit()
        scheduler.catch_up()
        assert ran == ["stock_backfill"]
        inst.history_start, inst.history_complete = date(2023, 5, 1), True  # listed in 2023: complete all the same
        db.commit()
    ran.clear()
    scheduler.catch_up()
    assert ran == ["stock_backtests"]


def test_heavy_jobs_skip_when_recent_unless_run_by_hand(monkeypatch):
    calls = []
    monkeypatch.setitem(
        scheduler.JOBS,
        "stock_universe",
        scheduler.JobSpec("stock_universe", "x", lambda db, p: calls.append(1) or "scanned", [], skip_if_fresh=timedelta(days=25)),
    )
    with SessionLocal() as db:
        db.add(JobRun(job_name="stock_universe", status="ok"))
        db.commit()
    scheduler.run_job("stock_universe", "schedule")
    assert calls == []
    scheduler.run_job("stock_universe", "manual by me")
    assert calls == [1]
    with SessionLocal() as db:
        assert [r.status for r in db.query(JobRun).filter_by(job_name="stock_universe").order_by(JobRun.id)] == ["ok", "skipped", "ok"]


def test_nightly_backup_writes_a_copy():
    from app.config import get_config

    assert scheduler.run_job("db_backup", "test")
    with SessionLocal() as db:
        run = scheduler.last_run(db, "db_backup")
    assert run.status == "ok", run.detail
    backups = list((get_config().data_dir / "backups").glob("niveshmitra-*-nightly.db"))
    assert backups and backups[0].stat().st_size > 0


def test_manual_run_endpoint(signed_in, monkeypatch):
    monkeypatch.setattr(scheduler, "run_job_async", lambda name, trigger="manual": True)
    r = signed_in.post("/api/data/jobs/amfi_nav_daily/run", headers=CSRF)
    assert r.status_code == 202 and r.json()["started"] is True
    assert signed_in.post("/api/data/jobs/nope/run", headers=CSRF).status_code == 404


def test_nav_date_is_the_one_most_funds_are_priced_on(signed_in, sources):  # noqa: F811
    """Liquid funds publish weekend NAVs ahead of time; the dashboard must not show that future date for everything."""
    from app.db.models import MfScheme

    with SessionLocal() as db:
        _full_sync(db)
        ahead = db.query(MfScheme).filter(MfScheme.is_active.is_(True)).first()
        ahead.latest_nav_date = date(2026, 10, 4)
        db.commit()
    assert signed_in.get("/api/data/status").json()["nav"]["latest_nav_date"] == "2026-09-29"
