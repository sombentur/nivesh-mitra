"""Ticker and market widgets (information, not advice)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db.base import get_db
from app.db.models import User
from app.services import market as svc
from app.services import sectors as sectors_svc

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/snapshot")
def snapshot(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return {k: v for k, v in svc.snapshot(db).items() if not k.startswith("_")}


@router.get("/ticker")
def ticker(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return svc.ticker(db)


@router.get("/sectors")
def sectors(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Every sector: its index move and how its tracked companies did today."""
    return sectors_svc.overview(db)


@router.get("/sectors/{key}")
def sector(key: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """One sector's index history and its companies, grouped by industry."""
    try:
        return sectors_svc.detail(db, key)
    except sectors_svc.UnknownSector:
        raise HTTPException(404, "No such sector") from None
