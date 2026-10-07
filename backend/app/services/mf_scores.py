"""Mutual fund expense ratios (AMFI) and category scores (doc 03 Part C)."""

from collections import defaultdict
from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.connectors import amfi_ter
from app.connectors.http import SourceUnavailable
from app.db.base import utcnow
from app.db.models import FundScore, MfScheme, MfSchemeFacts, ScoreRun
from app.engines import mf_metrics as mm
from app.engines import mf_scoring as sc
from app.rules import load_rules
from app.services import mf_data, strategy_versions

Progress = Callable[[int, int], None]
KEEP_RUNS = 8
SOURCE_TER = "amfi_ter"


def _noop(_d: int, _t: int) -> None:
    pass


def rules() -> dict:
    return load_rules("mf_scoring")


# ------------------------------------------------------------------------------------------------ expense ratios
def sync_ter(db: Session, progress: Progress = _noop) -> str:
    """This month's TER for every scheme (early in a month, last month's file is used too)."""
    today = utcnow().date()
    months = [today.replace(day=1)]
    if today.day <= 5:
        months.insert(0, (today.replace(day=1) - timedelta(days=1)).replace(day=1))
    rows: list[amfi_ter.TerRow] = []
    for m in months:
        try:
            rows += amfi_ter.fetch_month(m)
        except SourceUnavailable:
            if m == months[-1] and not rows:
                raise
    latest = amfi_ter.latest_per_scheme(rows)
    if not latest:
        raise SourceUnavailable("AMFI's TER file had no rows")
    updated = 0
    for s in db.scalars(select(MfScheme).where(MfScheme.is_active.is_(True), MfScheme.plan.in_(("direct", "regular")))):
        t = latest.get(amfi_ter.normalise_name(s.fund_name))
        if t is None:
            continue
        ter, fee = (t.direct_ter, t.direct_fee) if s.plan == "direct" else (t.regular_ter, t.regular_fee)
        if ter is None:
            continue
        as_of = t.ter_date.replace(day=1)
        row = db.get(MfSchemeFacts, {"scheme_code": s.scheme_code, "as_of": as_of}) or MfSchemeFacts(scheme_code=s.scheme_code, as_of=as_of)
        row.ter, row.fee, row.ter_date, row.source, row.fetched_at = ter, fee, t.ter_date, SOURCE_TER, utcnow()
        db.add(row)
        updated += 1
    mf_data.set_status(db, SOURCE_TER, True, sla_minutes=60 * 24 * 40)
    db.commit()
    return f"Expense ratios for {updated} fund plans (AMFI data to {max(r.ter_date for r in latest.values()):%d %b %Y})"


def latest_ter(db: Session) -> dict[int, float]:
    """Newest TER per scheme."""
    newest = select(MfSchemeFacts.scheme_code, func.max(MfSchemeFacts.as_of).label("m")).where(MfSchemeFacts.ter.is_not(None)).group_by(MfSchemeFacts.scheme_code).subquery()
    stmt = select(MfSchemeFacts.scheme_code, MfSchemeFacts.ter).join(
        newest, (MfSchemeFacts.scheme_code == newest.c.scheme_code) & (MfSchemeFacts.as_of == newest.c.m)
    )
    return {c: t for c, t in db.execute(stmt)}


def latest_fee(db: Session, scheme_code: int) -> float | None:
    """The fund house's own fee from the newest TER row (None for months before AMFI split it out)."""
    return db.scalar(
        select(MfSchemeFacts.fee).where(MfSchemeFacts.scheme_code == scheme_code, MfSchemeFacts.ter.is_not(None)).order_by(MfSchemeFacts.as_of.desc()).limit(1)
    )


def ter_history(db: Session, scheme_code: int) -> list[tuple[date, float]]:
    return [(d, t) for d, t in db.execute(select(MfSchemeFacts.as_of, MfSchemeFacts.ter).where(MfSchemeFacts.scheme_code == scheme_code, MfSchemeFacts.ter.is_not(None)).order_by(MfSchemeFacts.as_of))]


# ------------------------------------------------------------------------------------------------ scoring
def _series(db: Session, code: int) -> pd.Series:
    return mm.to_series(mf_data.nav_series(db, code))


def _synthetic_index(series: list[pd.Series]) -> pd.Series:
    """A 'typical fund tracking this index': the median daily return of the group, compounded."""
    rets = pd.concat([s.pct_change() for s in series], axis=1).median(axis=1, skipna=True).dropna()
    return (1 + rets).cumprod() * 100


def run_scoring(db: Session, progress: Progress = _noop) -> str:
    r = rules()
    funds = db.scalars(select(MfScheme).where(MfScheme.tracked.is_(True), MfScheme.history_synced_at.is_not(None))).all()
    if not funds:
        raise SourceUnavailable("No fund history yet — scoring runs after the history download")
    as_of_d = max(f.latest_nav_date for f in funds if f.latest_nav_date)
    as_of = pd.Timestamp(as_of_d)
    ends = mm.grid(as_of, r["lookback_years"])
    rf = r["risk_free_rate"]
    ter = latest_ter(db)

    # Peer groups: active funds by category; index funds by the index they track (others stay unranked).
    groups: dict[tuple[str, str], list[MfScheme]] = defaultdict(list)
    index_label: dict[str, str] = {}
    for f in funds:
        if f.asset_class == "Index":
            g = sc.index_group(f.display_name or f.fund_name, r)
            key = g["key"] if g else "other_index"
            index_label[key] = g["label"] if g else "other indices"
            groups[("index", key)].append(f)
        else:
            groups[("category", f.category)].append(f)

    # Benchmark stand-ins: the longest-running index fund on each benchmark.
    proxies: dict[str, tuple[MfScheme, pd.Series]] = {}
    for key in set(r["benchmark_proxy"].values()):
        cands = [f for f in groups.get(("index", key), []) if f.history_start]
        if cands:
            best = min(cands, key=lambda f: (f.history_start, f.scheme_code))
            proxies[key] = (best, _series(db, best.scheme_code))

    version = strategy_versions.get_or_create(db, "mf", r)
    run = ScoreRun(engine="mf", strategy_version_id=version.id, data_as_of=as_of_d, universe_size=len(funds), status="running")
    db.add(run)
    db.commit()  # short write transactions: other jobs (e.g. stock downloads) write to the same database

    done = 0
    for (kind, key), members in groups.items():
        if kind == "index":
            model, label, ctx = "index", index_label[key], {"category": f"{index_label[key]} index", "bench_label": index_label[key]}
        else:
            model = sc.model_for(members[0].asset_class, key, r)
            proxy_key = r["benchmark_proxy"].get(key)
            ctx = {"category": key, "bench_label": f"{proxies[proxy_key][0].display_name.split(' - ')[0]}" if proxy_key in proxies else None}
            label = key
        if model is None:
            continue
        series = {f.scheme_code: _series(db, f.scheme_code) for f in members}
        bench = proxies[r["benchmark_proxy"][key]][1] if kind == "category" and r["benchmark_proxy"].get(key) in proxies else None
        metrics: dict[int, dict] = {}
        rolls: dict[int, mm.Rolling] = {}
        for f in members:
            s = series[f.scheme_code]
            if s.empty:
                continue
            m, roll = mm.fund_metrics(s, as_of, ends, rf, bench)
            m["ter"] = ter.get(f.scheme_code)
            if f.twin_scheme_code and ter.get(f.twin_scheme_code) is not None and m["ter"] is not None:
                m["regular_cost_gap"] = max(0.0, ter[f.twin_scheme_code] - m["ter"])
            metrics[f.scheme_code], rolls[f.scheme_code] = m, roll
        # Peer-relative metrics
        if model in ("equity", "debt"):
            med3 = mm.median_series([x.rr3 for x in rolls.values()])
            med1 = mm.median_series([x.rr1 for x in rolls.values()])
            for code, roll in rolls.items():
                metrics[code]["beat_cat_3y"] = mm.share_above(roll.rr3, med3)
                metrics[code]["beat_cat_1y"] = mm.share_above(roll.rr1, med1)
        if model == "index" and key != "other_index" and len(series) >= 2:
            ref = _synthetic_index([s for s in series.values() if not s.empty])
            for code in metrics:
                s = series[code]
                metrics[code]["tracking_error_1y"], metrics[code]["tracking_diff_1y"] = mm.tracking(s, ref, 1, as_of)
                metrics[code]["tracking_error_3y"], metrics[code]["tracking_diff_3y"] = mm.tracking(s, ref, 3, as_of)
        if model == "index" and key == "other_index":
            scored = {c: sc.Scored(c, None, None, 0, 0.0, "unranked", unranked_reason="Tracks a less common index — not compared") for c in metrics}
        else:
            na = frozenset({"beat_bench_3y", "downcap_3y"}) if model == "equity" and bench is None else frozenset()
            scored = sc.score_group(metrics, model, r, ctx, not_applicable=na)
        for code, s in scored.items():
            db.add(
                FundScore(
                    run_id=run.id, scheme_code=code, peer_group=label, model=model, total=s.total, rank=s.rank, peers=s.peers,
                    confidence=s.confidence, coverage=s.coverage, components_json=s.components, metrics_json=_clean(metrics[code]),
                    reasons_for_json=s.reasons_for, reasons_against_json=s.reasons_against, unranked_reason=s.unranked_reason,
                )
            )
        done += len(members)
        db.commit()  # one peer group at a time
        progress(done, len(funds))
    run.status = "ok"  # only now does this run become "the latest scores"
    db.commit()
    _prune(db)
    ranked = db.scalar(select(func.count()).where(FundScore.run_id == run.id, FundScore.total.is_not(None)))
    return f"Scored {ranked} of {len(funds)} funds in {len(groups)} peer groups (NAVs to {as_of_d:%d %b %Y})"


def _clean(m: dict) -> dict:
    return {k: (None if v is None or (isinstance(v, float) and v != v) else round(float(v), 6)) for k, v in m.items()}


def _prune(db: Session) -> None:
    keep = [i for (i,) in db.execute(select(ScoreRun.id).where(ScoreRun.engine == "mf", ScoreRun.status == "ok").order_by(ScoreRun.id.desc()).limit(KEEP_RUNS))]
    if keep:
        db.execute(delete(FundScore).where(FundScore.run_id.not_in(keep)))
        db.commit()


def latest_run(db: Session) -> ScoreRun | None:
    return db.scalar(select(ScoreRun).where(ScoreRun.engine == "mf", ScoreRun.status == "ok").order_by(ScoreRun.id.desc()))


def score_for(db: Session, scheme_code: int) -> FundScore | None:
    run = latest_run(db)
    return db.get(FundScore, {"run_id": run.id, "scheme_code": scheme_code}) if run else None


def top_in(db: Session, category: str | None = None, index_group_label: str | None = None, limit: int = 10) -> list[tuple[MfScheme, FundScore]]:
    run = latest_run(db)
    if run is None:
        return []
    stmt = select(MfScheme, FundScore).join(FundScore, FundScore.scheme_code == MfScheme.scheme_code).where(FundScore.run_id == run.id, FundScore.total.is_not(None))
    if category:
        stmt = stmt.where(MfScheme.category == category, FundScore.model != "index")
    if index_group_label:
        stmt = stmt.where(FundScore.model == "index", FundScore.peer_group == index_group_label)
    return [(s, f) for s, f in db.execute(stmt.order_by(FundScore.total.desc()).limit(limit))]
