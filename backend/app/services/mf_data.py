"""Keeping mutual fund data fresh: scheme master, daily NAVs, one-time history download, gap filling.

Every function is safe to re-run (idempotent) — the scheduler can call them as often as it likes.
"""

import time
from collections.abc import Callable, Iterable
from datetime import date, timedelta

from sqlalchemy import func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.connectors import amfi, mfapi
from app.connectors.http import SourceUnavailable
from app.db.base import utcnow
from app.db.models import DataSourceStatus, MfScheme, NavDaily
from app.engines import mf_catalog as catalog
from app.rules import load_rules

Progress = Callable[[int, int], None]

SOURCE_NAV = "amfi_nav"
SOURCE_MASTER = "amfi_master"
SOURCE_HISTORY = "mf_history"
GAP_FILL_MAX_DAYS = 90
GAP_CHUNK_DAYS = 30
MFAPI_PAUSE_SECONDS = 0.15


def _rules() -> dict:
    return load_rules("mf_categories")


def _noop(_done: int, _total: int) -> None:
    pass


def _scheme_type(raw: str) -> str:
    r = raw.lower()
    if r.startswith("open"):
        return "Open Ended Schemes"
    if r.startswith("close"):
        return "Close Ended Schemes"
    if r.startswith("interval"):
        return "Interval Fund Schemes"
    return raw


def set_status(db: Session, source: str, ok: bool, error: str | None = None, sla_minutes: int = 1440) -> None:
    row = db.get(DataSourceStatus, source) or DataSourceStatus(source=source, freshness_sla_minutes=sla_minutes)
    now = utcnow()
    row.last_attempt_at = now
    if ok:
        row.last_success_at = now
        row.last_error = None
    else:
        row.last_error = (error or "failed")[:1000]
    row.healthy = ok
    db.add(row)


def insert_navs(db: Session, rows: Iterable[tuple[int, date, float]]) -> int:
    """Insert NAV rows, silently skipping ones already stored."""
    values = [{"scheme_code": c, "date": d, "nav": n} for c, d, n in rows]
    if not values:
        return 0
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        stmt = sqlite_insert(NavDaily).on_conflict_do_nothing()
    elif dialect == "postgresql":
        stmt = pg_insert(NavDaily).on_conflict_do_nothing()
    else:
        stmt = insert(NavDaily)
    for i in range(0, len(values), 5000):
        db.execute(stmt, values[i : i + 5000])
    return len(values)


def _classify(s: MfScheme, plan_raw: str, option_raw: str, raw_category: str, scheme_type: str, rules: dict) -> None:
    s.plan = catalog.plan_of(plan_raw, s.display_name or "", s.fund_name)
    s.option, s.option_detail = catalog.option_of(option_raw, s.display_name or "", s.fund_name)
    s.scheme_type = scheme_type
    cat = catalog.categorise(raw_category, s.fund_name, scheme_type, rules)
    s.asset_class, s.category, s.raw_category = cat.asset_class, cat.category, raw_category


def _update_tracked(s: MfScheme, rules: dict) -> None:
    s.tracked = bool(
        s.is_active
        and s.plan == "direct"
        and s.option == "growth"
        and s.scheme_type == rules["open_ended_type"]
        and s.asset_class in rules["tracked_asset_classes"]
    )


def link_twins(db: Session) -> int:
    """Pair each Direct plan with its Regular plan (same AMC, same fund variant, same option)."""
    by_key: dict[tuple[str, str], dict[str, MfScheme]] = {}
    for s in db.scalars(select(MfScheme).where(MfScheme.variant_key.is_not(None), MfScheme.is_active.is_(True))):
        by_key.setdefault((s.variant_key, s.option), {})[s.plan] = s
    linked = 0
    for plans in by_key.values():
        d, r = plans.get("direct"), plans.get("regular")
        if d and r:
            d.twin_scheme_code, r.twin_scheme_code = r.scheme_code, d.scheme_code
            linked += 1
    return linked


def sync_scheme_master(db: Session, progress: Progress = _noop) -> str:
    rules = _rules()
    try:
        rows = amfi.fetch_scheme_master()
    except SourceUnavailable as exc:
        set_status(db, SOURCE_MASTER, False, str(exc), sla_minutes=60 * 24 * 8)
        db.commit()
        raise
    existing = {s.scheme_code: s for s in db.scalars(select(MfScheme))}
    for i, r in enumerate(rows):
        s = existing.get(r.scheme_code)
        if s is None:
            s = MfScheme(scheme_code=r.scheme_code, fund_name=r.fund_name, is_active=False, tracked=False)
            db.add(s)
            existing[r.scheme_code] = s
            _classify(s, "", "", r.raw_category, _scheme_type(r.scheme_type), rules)
        s.amc = r.amc
        s.display_name = catalog.display_name(r.nav_name, r.fund_name, s.plan, s.option_detail or "")
        s.launch_date = r.launch_date
        s.isin_growth = s.isin_growth or r.isin_growth
        s.isin_reinvest = s.isin_reinvest or r.isin_reinvest
        s.variant_key = catalog.variant_key(r.amc, r.nav_name or r.fund_name)
        s.updated_at = utcnow()
        if i % 2000 == 0:
            progress(i, len(rows))
    db.flush()
    twins = link_twins(db)
    set_status(db, SOURCE_MASTER, True, sla_minutes=60 * 24 * 8)
    db.commit()
    return f"{len(rows)} schemes in AMFI's master list; {twins} Direct/Regular pairs linked"


def update_daily_navs(db: Session, progress: Progress = _noop) -> str:
    rules = _rules()
    try:
        rows = amfi.fetch_nav_all()
    except SourceUnavailable as exc:
        set_status(db, SOURCE_NAV, False, str(exc))
        db.commit()
        raise
    if not rows:
        raise SourceUnavailable("AMFI's NAV file was empty")
    latest = max(r.nav_date for r in rows)
    active_cutoff = latest - timedelta(days=rules["active_within_days"])
    existing = {s.scheme_code: s for s in db.scalars(select(MfScheme))}

    new_navs: list[tuple[int, date, float]] = []
    gapped: list[tuple[MfScheme, amfi.NavRow]] = []  # funds whose history stops more than a few days back
    for r in rows:
        s = existing.get(r.scheme_code)
        if s is None:
            s = MfScheme(scheme_code=r.scheme_code, fund_name=r.fund_name, display_name="", tracked=False)
            db.add(s)
            existing[r.scheme_code] = s
        s.fund_name = r.fund_name
        _classify(s, r.plan_raw, r.option_raw, r.raw_category, r.scheme_type or "Open Ended Schemes", rules)
        if not s.display_name:
            s.display_name = catalog.display_name(None, r.fund_name, s.plan, s.option_detail or "")
        s.isin_growth = r.isin_growth or s.isin_growth
        s.isin_reinvest = r.isin_reinvest or s.isin_reinvest
        if r.nav:
            s.latest_nav, s.latest_nav_date = r.nav, r.nav_date
        s.is_active = bool(r.nav) and r.nav_date >= active_cutoff
        _update_tracked(s, rules)
        s.updated_at = utcnow()
        if s.history_synced_at and r.nav:
            if s.history_end and s.history_end < r.nav_date - timedelta(days=3):
                gapped.append((s, r))  # history_end only moves once the gap is really filled
            else:
                new_navs.append((s.scheme_code, r.nav_date, r.nav))
                s.history_end = max(s.history_end or r.nav_date, r.nav_date)
    db.flush()
    insert_navs(db, new_navs)
    link_twins(db)  # activity may have changed, so re-pair Direct/Regular plans
    db.commit()

    gap_note = "; " + fill_gaps(db, gapped, latest) if gapped else ""
    set_status(db, SOURCE_NAV, True)
    db.commit()
    active = sum(1 for s in existing.values() if s.is_active)
    return f"NAVs up to {latest:%d %b %Y} for {active} active schemes; {len(new_navs)} added to history{gap_note}"


def fill_gaps(db: Session, gapped: list[tuple[MfScheme, amfi.NavRow]], latest: date) -> str:
    """Days the PC was off: one AMFI history download covers every fund.

    If that fails, or the gap is very long, the funds are queued for mfapi.in, which re-fetches from their last stored date.
    """
    start = min(s.history_end for s, _ in gapped) + timedelta(days=1)
    if (latest - start).days > GAP_FILL_MAX_DAYS:
        return _requeue(db, gapped, f"gap of {(latest - start).days} days")
    codes = {s.scheme_code for s, _ in gapped}
    added = 0
    try:
        cursor = start
        while cursor <= latest:
            chunk_end = min(latest, cursor + timedelta(days=GAP_CHUNK_DAYS - 1))
            rows = amfi.fetch_nav_history(cursor, chunk_end)
            added += insert_navs(db, [(r.scheme_code, r.nav_date, r.nav) for r in rows if r.nav and r.scheme_code in codes])
            cursor = chunk_end + timedelta(days=1)
    except SourceUnavailable as exc:
        db.rollback()
        return _requeue(db, gapped, f"AMFI history unavailable ({exc})")
    insert_navs(db, [(s.scheme_code, r.nav_date, r.nav) for s, r in gapped])
    for s, r in gapped:
        s.history_end = max(s.history_end, r.nav_date)
    db.commit()
    return f"filled missed days {start:%d %b}–{latest:%d %b} for {len(gapped)} funds ({added} NAVs)"


def _requeue(db: Session, gapped: list[tuple[MfScheme, amfi.NavRow]], why: str) -> str:
    for s, _ in gapped:
        s.history_synced_at = None  # backfill re-fetches from history_end + 1 via mfapi.in
    db.commit()
    return f"{why}: {len(gapped)} funds queued for re-download"


def _store_history(db: Session, s: MfScheme, points: list[tuple[date, float]]) -> None:
    insert_navs(db, [(s.scheme_code, d, n) for d, n in points])
    if points:
        s.history_start = min(filter(None, [s.history_start, points[0][0]]))
        s.history_end = max(filter(None, [s.history_end, points[-1][0]]))
    s.history_synced_at = utcnow()
    s.history_error = None


def pending_history(db: Session) -> list[MfScheme]:
    order = {c: i for i, c in enumerate(["Equity", "Index", "Hybrid", "Debt", "Solution", "Life Cycle", "FoF"])}
    rows = db.scalars(select(MfScheme).where(MfScheme.tracked.is_(True), MfScheme.history_synced_at.is_(None))).all()
    return sorted(rows, key=lambda s: (order.get(s.asset_class, 99), s.category, s.scheme_code))


def backfill_history(db: Session, progress: Progress = _noop) -> str:
    pending = pending_history(db)
    ok = failed = 0
    for i, s in enumerate(pending):
        start = s.history_end + timedelta(days=1) if s.history_end else None
        try:
            points = mfapi.fetch_history(s.scheme_code, start)
        except SourceUnavailable as exc:
            s.history_error = str(exc)[:300]
            failed += 1
        else:
            _store_history(db, s, points)
            ok += 1
        db.commit()
        progress(i + 1, len(pending))
        time.sleep(MFAPI_PAUSE_SECONDS)
    counts = history_counts(db)
    set_status(db, SOURCE_HISTORY, failed == 0 or ok > 0, f"{failed} funds failed" if failed else None)
    db.commit()
    return f"downloaded {ok} funds' history ({failed} failed); {counts['synced']} of {counts['tracked']} funds complete"


def ensure_history(db: Session, scheme_code: int) -> MfScheme:
    """Download one fund's full history right now (used when you open a fund that isn't pre-downloaded)."""
    s = db.get(MfScheme, scheme_code)
    if s is None:
        raise KeyError(scheme_code)
    _store_history(db, s, mfapi.fetch_history(scheme_code))
    db.commit()
    return s


def history_counts(db: Session) -> dict:
    tracked = db.scalar(select(func.count()).where(MfScheme.tracked.is_(True))) or 0
    synced = db.scalar(select(func.count()).where(MfScheme.tracked.is_(True), MfScheme.history_synced_at.is_not(None))) or 0
    failed = db.scalar(
        select(func.count()).where(
            MfScheme.tracked.is_(True), MfScheme.history_synced_at.is_(None), MfScheme.history_error.is_not(None)
        )
    ) or 0
    return {"tracked": tracked, "synced": synced, "failed": failed}


def nav_series(db: Session, scheme_code: int) -> list[tuple[date, float]]:
    return [
        (d, n) for d, n in db.execute(select(NavDaily.date, NavDaily.nav).where(NavDaily.scheme_code == scheme_code).order_by(NavDaily.date))
    ]
