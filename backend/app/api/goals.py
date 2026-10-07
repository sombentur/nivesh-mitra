"""Your goals (question 10). The goal planner in step 4 adds the SIP maths on top of these."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db.base import get_db, utcnow
from app.db.models import Goal, User
from app.engines.plan import months_until
from app.engines.profile import future_value
from app.services import profile as profile_svc
from app.services.audit import audit

router = APIRouter(prefix="/api/goals", tags=["goals"])


class GoalBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    goal_type: str
    target_amount_today: int = Field(gt=0, le=10_000_000_000)
    target_year: int
    current_corpus: int = Field(default=0, ge=0, le=10_000_000_000)
    priority: int = Field(default=2, ge=1, le=3)
    inflation_rate: float | None = Field(default=None, ge=0, le=0.2)

    @field_validator("target_year")
    @classmethod
    def _year(cls, v: int) -> int:
        this_year = utcnow().year
        if not this_year <= v <= this_year + 60:
            raise ValueError(f"Target year must be between {this_year} and {this_year + 60}")
        return v


def _goal_types() -> dict[str, dict]:
    return {g["value"]: g for g in profile_svc.rules()["questions"]["goal_types"]}


def _view(g: Goal) -> dict:
    months = months_until(g.target_year, utcnow().date())  # to the middle of the goal year, as the plan does
    return {
        "id": g.id,
        "name": g.name,
        "goal_type": g.goal_type,
        "target_amount_today": g.target_amount_today,
        "inflation_rate": g.inflation_rate,
        "target_year": g.target_year,
        "years_away": round(months / 12, 1),
        "target_amount_future": future_value(g.target_amount_today, g.inflation_rate, months / 12),
        "current_corpus": g.current_corpus,
        "priority": g.priority,
    }


def _apply(g: Goal, body: GoalBody) -> None:
    types = _goal_types()
    if body.goal_type not in types:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown goal type")
    g.name = body.name.strip()
    g.goal_type = body.goal_type
    g.target_amount_today = body.target_amount_today
    g.target_year = body.target_year
    g.current_corpus = body.current_corpus
    g.priority = body.priority
    g.inflation_rate = body.inflation_rate if body.inflation_rate is not None else types[body.goal_type]["inflation"]


def _get(db: Session, user: User, goal_id: int) -> Goal:
    g = db.get(Goal, goal_id)
    if g is None or g.user_id != user.id or g.archived_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Goal not found")
    return g


@router.get("")
def list_goals(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(
        select(Goal).where(Goal.user_id == user.id, Goal.archived_at.is_(None)).order_by(Goal.priority, Goal.target_year)
    ).all()
    return [_view(g) for g in rows]


@router.post("")
def create_goal(body: GoalBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    g = Goal(user_id=user.id)
    _apply(g, body)
    db.add(g)
    audit(db, user.email, "goal_created", name=g.name)
    db.commit()
    return _view(g)


@router.put("/{goal_id}")
def update_goal(goal_id: int, body: GoalBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    g = _get(db, user, goal_id)
    _apply(g, body)
    audit(db, user.email, "goal_updated", goal_id=goal_id)
    db.commit()
    return _view(g)


@router.delete("/{goal_id}")
def archive_goal(goal_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    g = _get(db, user, goal_id)
    g.archived_at = utcnow()  # kept for history, hidden from lists
    audit(db, user.email, "goal_archived", goal_id=goal_id)
    db.commit()
    return {"ok": True}
