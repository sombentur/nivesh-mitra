"""Data health: how fresh each source is, background job status, and "update now" buttons."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import scheduler
from app.auth.deps import current_user
from app.db.base import get_db, utcnow
from app.db.models import MfScheme, User
from app.services import mf_data
from app.services import refresh
from app.services.audit import audit

router = APIRouter(prefix="/api/data", tags=["data"])
NAV_STALE_AFTER_DAYS = 4  # weekend + a holiday


def _run_view(run) -> dict | None:
    if run is None:
        return None
    return {
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "detail": run.detail,
    }


@router.get("/freshness")
def freshness(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """How current the prices are and what is being downloaded right now (the Refresh button polls this)."""
    return refresh.freshness(db)


@router.post("/refresh", status_code=202)
def refresh_now(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Bring prices and NAVs up to date if they are behind; always re-read live quotes."""
    return refresh.start(db)


@router.get("/status")
def data_status(db: Session = Depends(get_db), user: User = Depends(current_user)):
    # The date most funds are priced on. (Not the newest date any fund has: liquid funds publish NAVs ahead for
    # weekends and holidays, which would show a date in the future.)
    latest = db.scalar(
        select(MfScheme.latest_nav_date)
        .where(MfScheme.is_active.is_(True), MfScheme.latest_nav_date.is_not(None))
        .group_by(MfScheme.latest_nav_date)
        .order_by(func.count().desc(), MfScheme.latest_nav_date.desc())
        .limit(1)
    )
    today = utcnow().date()
    jobs = []
    for spec in scheduler.JOBS.values():
        nxt = scheduler.next_run(spec.name)
        jobs.append(
            {
                "name": spec.name,
                "label": spec.label,
                "running": scheduler.is_running(spec.name),
                "progress": scheduler.progress(spec.name),
                "last_run": _run_view(scheduler.last_run(db, spec.name)),
                "last_success": _run_view(scheduler.last_success(db, spec.name)),
                "next_run_at": nxt.isoformat() if nxt else None,
            }
        )
    return {
        "nav": {
            "latest_nav_date": latest.isoformat() if latest else None,
            "fresh": bool(latest and latest >= today - timedelta(days=NAV_STALE_AFTER_DAYS)),
            "active_schemes": db.scalar(select(func.count()).where(MfScheme.is_active.is_(True))) or 0,
            **mf_data.history_counts(db),
        },
        "jobs": jobs,
    }


@router.post("/jobs/{name}/run", status_code=status.HTTP_202_ACCEPTED)
def run_now(name: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if name not in scheduler.JOBS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown job")
    started = scheduler.run_job_async(name, f"manual by {user.email}")
    audit(db, user.email, "job_run_requested", job=name, started=started)
    db.commit()
    return {"started": started, "already_running": not started}
