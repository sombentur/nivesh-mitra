"""Risk profile, asset split and onboarding steps (doc 03 Part A, doc 04 §8)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db.base import get_db, utcnow
from app.db.models import RiskProfile, User
from app.engines import profile as engine
from app.services import app_settings
from app.services import profile as svc
from app.services.audit import audit

router = APIRouter(prefix="/api", tags=["profile"])


class AllocationChange(BaseModel):
    core: int
    satellite: int
    trading: int
    reason: str | None = None


def _require_profile(db: Session, user: User) -> RiskProfile:
    profile = svc.current_profile(db, user)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No risk profile yet. Complete onboarding first.")
    return profile


@router.get("/profile/rules")
def profile_rules(user: User = Depends(current_user)):
    r = svc.rules()
    return {
        "version": r["version"],
        "questions": r["questions"],
        "splits": r["splits"],
        "limits": r["limits"],
        "emergency_fund": r["emergency_fund"],
        "paper_trading_days": r["paper_trading_days"],
        "sebi_reality_check": r["sebi_reality_check"],
    }


@router.post("/profile")
def submit_profile(answers: engine.ProfileAnswers, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        profile = svc.save_profile(db, user, answers)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    audit(db, user.email, "risk_profile_saved", category=profile.final_category, rules_version=svc.rules()["version"])
    db.commit()
    return svc.profile_view(db, profile)


@router.get("/profile")
def get_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return svc.profile_view(db, _require_profile(db, user))


@router.get("/profile/history")
def profile_history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(RiskProfile).where(RiskProfile.user_id == user.id).order_by(RiskProfile.id.desc())).all()
    return [
        {"id": p.id, "created_at": p.created_at.isoformat(), "category": p.final_category, "is_current": p.is_current}
        for p in rows
    ]


@router.post("/profile/split-check")
def split_check(body: AllocationChange, user: User = Depends(current_user)):
    """Live warnings while you drag the sliders; saves nothing."""
    try:
        split = engine.Split(core=body.core, satellite=body.satellite, trading=body.trading)
        engine.check_split_allowed(split, svc.rules())
    except (ValidationError, ValueError) as exc:
        return {"ok": False, "error": _message(exc), "warnings": []}
    return {"ok": True, "error": None, "warnings": engine.split_warnings(split, svc.rules())}


@router.put("/profile/allocation")
def change_allocation(body: AllocationChange, db: Session = Depends(get_db), user: User = Depends(current_user)):
    profile = _require_profile(db, user)
    try:
        split = engine.Split(core=body.core, satellite=body.satellite, trading=body.trading)
        target = svc.change_allocation(db, profile, split, body.reason)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _message(exc))
    audit(
        db,
        user.email,
        "allocation_changed",
        split=split.model_dump(),
        effective_at=target.effective_at.isoformat(),
        reason=target.reason,
        warnings=target.warnings_json,
    )
    db.commit()
    return svc.profile_view(db, profile)


@router.delete("/profile/allocation/pending")
def cancel_pending_allocation(db: Session = Depends(get_db), user: User = Depends(current_user)):
    profile = _require_profile(db, user)
    if svc.cancel_pending(db, profile):
        audit(db, user.email, "allocation_pending_cancelled")
        db.commit()
    return svc.profile_view(db, profile)


@router.get("/onboarding/status")
def onboarding_status(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return svc.onboarding_status(db, user)


@router.post("/onboarding/sebi-ack")
def sebi_ack(db: Session = Depends(get_db), user: User = Depends(current_user)):
    app_settings.set_setting(db, "sebi_ack_at", utcnow().isoformat())
    audit(db, user.email, "sebi_reality_check_acknowledged")
    db.commit()
    return svc.onboarding_status(db, user)


@router.post("/onboarding/complete")
def complete(db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = svc.onboarding_status(db, user)
    if not (s["profile_done"] and s["sebi_acknowledged"]):
        raise HTTPException(status.HTTP_409_CONFLICT, "Finish the questionnaire and the SEBI reality check first.")
    if not s["paper_started"]:
        app_settings.set_setting(db, "paper_mode_start", utcnow().date().isoformat())
        audit(db, user.email, "paper_mode_started")
        db.commit()
    return svc.onboarding_status(db, user)


def _message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
    return str(exc)
