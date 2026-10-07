"""Settings and connections. Secret values can be written but are never returned — only a masked status."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db.base import get_db
from app.db.models import User
from app.security import secrets_store
from app.services import app_settings
from app.services.audit import audit

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SecretBody(BaseModel):
    value: str


@router.get("")
def get_settings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return app_settings.all_settings(db)


@router.patch("")
def update_settings(changes: dict[str, Any], db: Session = Depends(get_db), user: User = Depends(current_user)):
    for key, value in changes.items():
        if key not in app_settings.USER_EDITABLE_KEYS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown setting: {key}")
        try:
            app_settings.set_setting(db, key, value)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    audit(db, user.email, "settings_changed", changes=changes)
    db.commit()
    return app_settings.all_settings(db)


@router.get("/secrets")
def list_secrets(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [s.__dict__ for s in secrets_store.list_status(db)]


@router.put("/secrets/{name}")
def put_secret(name: str, body: SecretBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        secrets_store.set_secret(db, name, body.value)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown key name")
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The value is empty")
    audit(db, user.email, "secret_set", name=name)  # never the value
    db.commit()
    return {"ok": True}


@router.delete("/secrets/{name}")
def delete_secret(name: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if name not in secrets_store.KNOWN_SECRETS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown key name")
    secrets_store.delete_secret(db, name)
    audit(db, user.email, "secret_deleted", name=name)
    db.commit()
    return {"ok": True}
