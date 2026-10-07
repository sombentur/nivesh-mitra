"""Saving and reading the risk profile, asset split, onboarding and paper-mode state."""

from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import AllocationTarget, RiskProfile, User
from app.engines import profile as engine
from app.rules import load_rules
from app.services import app_settings, strategy_versions


def rules() -> dict:
    return load_rules("profile")


def current_profile(db: Session, user: User) -> RiskProfile | None:
    return db.scalar(
        select(RiskProfile).where(RiskProfile.user_id == user.id, RiskProfile.is_current.is_(True)).order_by(RiskProfile.id.desc())
    )


def save_profile(db: Session, user: User, answers: engine.ProfileAnswers) -> RiskProfile:
    r = rules()
    result = engine.assess(answers, r)
    version = strategy_versions.get_or_create(db, "profile", r)
    for old in db.scalars(select(RiskProfile).where(RiskProfile.user_id == user.id, RiskProfile.is_current.is_(True))):
        old.is_current = False
    now = utcnow()
    profile = RiskProfile(
        user_id=user.id,
        strategy_version_id=version.id,
        answers_json=answers.model_dump(),
        result_json=result.model_dump(),
        capacity_score=result.capacity_score,
        tolerance_category=result.tolerance_category,
        final_category=result.final_category,
        created_at=now,
        review_due_on=now.date() + relativedelta(months=r["review_months"]),
        is_current=True,
    )
    db.add(profile)
    db.flush()
    split = result.default_split
    db.add(
        AllocationTarget(
            profile_id=profile.id,
            core_pct=split.core,
            satellite_pct=split.satellite,
            trading_pct=split.trading,
            is_user_override=False,
            warnings_json=engine.split_warnings(split, r),
            created_at=now,
            effective_at=now,
        )
    )
    return profile


def _targets(db: Session, profile: RiskProfile) -> tuple[AllocationTarget | None, AllocationTarget | None]:
    """(split in effect now, pending split waiting for its delay)."""
    now = utcnow()
    rows = db.scalars(
        select(AllocationTarget).where(AllocationTarget.profile_id == profile.id).order_by(AllocationTarget.id.desc())
    ).all()
    active = next((t for t in rows if t.effective_at <= now), None)
    pending = next((t for t in rows if t.effective_at > now), None)
    return active, pending


def paper_status(db: Session) -> dict:
    start_raw = app_settings.get_setting(db, "paper_mode_start")
    days = rules()["paper_trading_days"]
    if not start_raw:
        return {"started_on": None, "ends_on": None, "days_left": days, "complete": False}
    start = date.fromisoformat(start_raw)
    ends = start + timedelta(days=days)
    today = utcnow().date()
    return {
        "started_on": start.isoformat(),
        "ends_on": ends.isoformat(),
        "days_left": max(0, (ends - today).days),
        "complete": today >= ends,
    }


def _split_dict(t: AllocationTarget) -> dict:
    return {"core": t.core_pct, "satellite": t.satellite_pct, "trading": t.trading_pct}


def profile_view(db: Session, profile: RiskProfile) -> dict:
    r = rules()
    result = engine.ProfileResult.model_validate(profile.result_json)
    active, pending = _targets(db, profile)
    split = engine.Split(**_split_dict(active))
    paper = paper_status(db)
    lock_reasons = engine.trading_lock_reasons(result.emergency.months_covered, paper["complete"], r) if split.trading else []
    return {
        "id": profile.id,
        "created_at": profile.created_at.isoformat(),
        "review_due_on": profile.review_due_on.isoformat(),
        "review_due": profile.review_due_on <= utcnow().date(),
        "rules_version": result.rules_version,
        "answers": profile.answers_json,
        "result": result.model_dump(),
        "allocation": {
            "target": split.model_dump(),
            "effective": engine.effective_split(split, bool(lock_reasons)).model_dump(),
            "is_user_override": active.is_user_override,
            "default": result.default_split.model_dump(),
            "warnings": engine.split_warnings(split, r),
            "trading_locked": bool(lock_reasons),
            "trading_lock_reasons": lock_reasons,
            "pending": {**_split_dict(pending), "effective_at": pending.effective_at.isoformat(), "reason": pending.reason}
            if pending
            else None,
        },
        "paper": paper,
    }


class ReasonRequired(ValueError):
    pass


def change_allocation(db: Session, profile: RiskProfile, split: engine.Split, reason: str | None) -> AllocationTarget:
    """Tightening applies now. Raising the trading share needs a typed reason and waits 24 hours (doc 04 §6)."""
    r = rules()
    engine.check_split_allowed(split, r)
    active, _ = _targets(db, profile)
    now = utcnow()
    effective_at: datetime = now
    if split.trading > active.trading_pct:
        if not reason or len(reason.strip()) < 10:
            raise ReasonRequired("Raising the trading share needs a reason of at least 10 characters.")
        effective_at = now + timedelta(hours=r["limits"]["loosen_delay_hours"])
    cancel_pending(db, profile)  # the newest decision wins; an older waiting change never activates
    default = engine.Split.model_validate(profile.result_json["default_split"])
    target = AllocationTarget(
        profile_id=profile.id,
        core_pct=split.core,
        satellite_pct=split.satellite,
        trading_pct=split.trading,
        is_user_override=split != default,
        reason=reason.strip() if reason else None,
        warnings_json=engine.split_warnings(split, r),
        created_at=now,
        effective_at=effective_at,
    )
    db.add(target)
    return target


def cancel_pending(db: Session, profile: RiskProfile) -> bool:
    now = utcnow()
    pending = db.scalars(
        select(AllocationTarget).where(AllocationTarget.profile_id == profile.id, AllocationTarget.effective_at > now)
    ).all()
    for row in pending:
        db.delete(row)
    return bool(pending)


def onboarding_status(db: Session, user: User) -> dict:
    profile_done = current_profile(db, user) is not None
    sebi_ack = app_settings.get_setting(db, "sebi_ack_at") is not None
    paper = paper_status(db)
    return {
        "profile_done": profile_done,
        "sebi_acknowledged": sebi_ack,
        "paper_started": paper["started_on"] is not None,
        "complete": profile_done and sebi_ack and paper["started_on"] is not None,
    }
