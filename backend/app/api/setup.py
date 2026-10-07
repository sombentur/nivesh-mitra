"""First-time setup: which Google login key (client ID) to use and which single email may sign in.

Open without login only until the first successful sign-in; after that it is locked.
"""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import User
from app.services.app_settings import get_setting, is_configured, set_setting
from app.services.audit import audit

router = APIRouter(prefix="/api/setup", tags=["setup"])

CLIENT_ID_RE = re.compile(r"^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SetupBody(BaseModel):
    google_client_id: str
    allowed_email: str

    @field_validator("google_client_id")
    @classmethod
    def _client_id(cls, v: str) -> str:
        v = v.strip()
        if not CLIENT_ID_RE.match(v):
            raise ValueError("This doesn't look like a Google client ID (it ends with .apps.googleusercontent.com)")
        return v

    @field_validator("allowed_email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v


def _locked(db: Session) -> bool:
    return db.scalar(select(User.id).limit(1)) is not None


@router.get("/status")
def setup_status(db: Session = Depends(get_db)):
    return {
        "configured": is_configured(db),
        "locked": _locked(db),
        "google_client_id": get_setting(db, "google_client_id"),
    }


@router.post("")
def save_setup(body: SetupBody, db: Session = Depends(get_db)):
    if _locked(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "Setup is locked after the first sign-in.")
    set_setting(db, "google_client_id", body.google_client_id)
    set_setting(db, "allowed_email", body.allowed_email)
    audit(db, "setup", "setup_saved", allowed_email=body.allowed_email)
    db.commit()
    return {"ok": True}
