"""News pulse: headlines + tone (information, not a forecast)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import scheduler
from app.auth.deps import current_user
from app.db.base import get_db
from app.db.models import User
from app.services import news as svc

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("")
def pulse(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return svc.pulse(db) | {"refreshing": scheduler.is_running("news_pulse")}


@router.post("/refresh", status_code=202)
def refresh(user: User = Depends(current_user)):
    return {"started": scheduler.run_job_async("news_pulse", "manual by you")}
