"""Mutual fund search and fund pages."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.connectors.http import SourceUnavailable
from app.db.base import get_db
from app.db.models import FundScore, MfScheme, User
from app.engines import mf_returns
from app.engines.plan import cost_of_regular
from app.services import mf_data, mf_scores

router = APIRouter(prefix="/api/mf", tags=["mutual funds"])


def _score_brief(f: FundScore | None) -> dict | None:
    if f is None:
        return None
    return {"total": f.total, "rank": f.rank, "peers": f.peers, "confidence": f.confidence, "peer_group": f.peer_group}


def _latest_scores(db: Session, codes: list[int]) -> dict[int, FundScore]:
    run = mf_scores.latest_run(db)
    if run is None or not codes:
        return {}
    return {f.scheme_code: f for f in db.scalars(select(FundScore).where(FundScore.run_id == run.id, FundScore.scheme_code.in_(codes)))}


def _brief(s: MfScheme, score: FundScore | None = None) -> dict:
    return {
        "scheme_code": s.scheme_code,
        "name": s.display_name or s.fund_name,
        "amc": s.amc,
        "asset_class": s.asset_class,
        "category": s.category,
        "plan": s.plan,
        "option": s.option,
        "latest_nav": s.latest_nav,
        "latest_nav_date": s.latest_nav_date.isoformat() if s.latest_nav_date else None,
        "tracked": s.tracked,
        "score": _score_brief(score),
    }


@router.get("/categories")
def categories(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.execute(
        select(MfScheme.asset_class, MfScheme.category, func.count())
        .where(MfScheme.tracked.is_(True))
        .group_by(MfScheme.asset_class, MfScheme.category)
        .order_by(MfScheme.asset_class, MfScheme.category)
    ).all()
    return [{"asset_class": a, "category": c, "count": n} for a, c, n in rows]


@router.get("/search")
def search(
    q: str = "",
    category: str | None = None,
    include_all: bool = False,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """By default only active Direct–Growth funds (the ones NiveshMitra compares). include_all adds every plan/option."""
    stmt = select(MfScheme)
    if include_all:
        stmt = stmt.where(MfScheme.is_active.is_(True))
    else:
        stmt = stmt.where(MfScheme.tracked.is_(True))
    if category:
        stmt = stmt.where(MfScheme.category == category)
    for word in q.split()[:6]:
        stmt = stmt.where(func.lower(MfScheme.display_name).contains(word.lower()))
    rows = db.scalars(stmt.order_by(MfScheme.display_name).limit(limit)).all()
    scores = _latest_scores(db, [s.scheme_code for s in rows])
    out = [_brief(s, scores.get(s.scheme_code)) for s in rows]
    if category:  # within one category, best score first
        out.sort(key=lambda x: (x["score"] is None or x["score"]["total"] is None, -((x["score"] or {}).get("total") or 0)))
    return out


@router.get("/schemes/{scheme_code}")
def scheme(scheme_code: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = db.get(MfScheme, scheme_code)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fund not found")
    series = mf_data.nav_series(db, scheme_code)
    twin = db.get(MfScheme, s.twin_scheme_code) if s.twin_scheme_code else None
    score = mf_scores.score_for(db, scheme_code)
    return {
        **_brief(s, score),
        "scoring": _scoring_view(db, score),
        "ter_history": [[d.isoformat(), t] for d, t in mf_scores.ter_history(db, scheme_code)],
        "fund_name": s.fund_name,
        "option_detail": s.option_detail,
        "scheme_type": s.scheme_type,
        "launch_date": s.launch_date.isoformat() if s.launch_date else None,
        "isin": s.isin_growth,
        "is_active": s.is_active,
        "twin": _brief(twin) if twin else None,
        "history": {
            "status": "ready" if series else ("failed" if s.history_error else "not_downloaded"),
            "error": s.history_error,
            "points": len(series),
        },
        "returns": mf_returns.summary(series),
        "chart": [[d.isoformat(), round(n, 4)] for d, n in mf_returns.downsample_weekly(series)],
    }


@router.post("/schemes/{scheme_code}/history")
def download_history(scheme_code: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        mf_data.ensure_history(db, scheme_code)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fund not found")
    except SourceUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Couldn't download history right now: {exc}")
    return scheme(scheme_code, db, user)


def _scoring_view(db: Session, f: FundScore | None) -> dict | None:
    """Everything behind the score: each metric's value, percentile and weight, plus plain-language reasons."""
    if f is None:
        return None
    m = f.metrics_json or {}
    gap = m.get("regular_cost_gap")
    run = mf_scores.latest_run(db)
    return {
        "total": f.total,
        "rank": f.rank,
        "peers": f.peers,
        "peer_group": f.peer_group,
        "model": f.model,
        "confidence": f.confidence,
        "coverage": f.coverage,
        "unranked_reason": f.unranked_reason,
        "components": f.components_json or {},
        "metrics": m,
        "reasons_for": f.reasons_for_json or [],
        "reasons_against": f.reasons_against_json or [],
        "regular_cost_10y_on_5000": round(cost_of_regular(5000, 0.10, gap)) if gap else None,
        "rules_version": mf_scores.rules()["version"],
        "as_of": run.data_as_of.isoformat() if run else None,
    }


@router.get("/scores")
def ranked(
    category: str | None = None,
    index_group: str | None = None,
    limit: int = Query(default=25, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Best-scored funds in one category (or one index group), highest first."""
    return [{**_brief(s, f), "reasons_for": f.reasons_for_json or []} for s, f in mf_scores.top_in(db, category, index_group, limit)]
