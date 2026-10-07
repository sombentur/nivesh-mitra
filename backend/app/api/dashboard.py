"""The decision-first dashboard in one call."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db.base import get_db
from app.db.models import User
from app.services import dashboard as svc

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return svc.build(db, user)
