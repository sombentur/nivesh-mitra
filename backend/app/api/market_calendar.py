"""Trading calendar: open days, holidays, how the market moved, and your practice results and dates."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db.base import get_db
from app.db.models import User
from app.services import market_calendar as svc

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("")
def calendar(start: date, end: date, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if end < start or (end - start).days > svc.MAX_DAYS:
        raise HTTPException(status_code=400, detail=f"Ask for between 1 and {svc.MAX_DAYS + 1} days")
    return svc.build(db, user, start, end)
