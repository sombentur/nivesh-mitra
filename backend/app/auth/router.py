"""Login flow: Google Sign-In → authenticator-app code (2FA) → session cookie.

1. POST /auth/google   verifies Google's ID token, checks the one allowed email, sets a short "pending" cookie
2. GET  /auth/totp/setup   first login only: returns a QR code for your authenticator app
3. POST /auth/totp     checks the 6-digit code, then issues the real session cookie
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import totp
from app.auth.deps import current_user
from app.auth.google import GoogleAuthError, verify_google_credential
from app.auth.sessions import (
    COOKIE_NAME,
    MAX_TOTP_ATTEMPTS,
    create_pending_session,
    create_web_session,
    find_session,
    revoke,
)
from app.config import get_config
from app.db.base import get_db, utcnow
from app.db.models import User
from app.security.crypto import decrypt, encrypt
from app.services.app_settings import get_setting, is_configured
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

PENDING_COOKIE = "nm_pending"


class GoogleLogin(BaseModel):
    credential: str


class TotpCode(BaseModel):
    code: str


def _set_cookie(response: Response, name: str, token: str, max_age: int) -> None:
    response.set_cookie(name, token, max_age=max_age, httponly=True, samesite="lax", secure=False, path="/")


def _pending_user(request: Request, db: Session) -> tuple[User, object]:
    row = find_session(db, request.cookies.get(PENDING_COOKIE), "pending_2fa")
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired. Please sign in with Google again.")
    return db.get(User, row.user_id), row


@router.post("/google")
def google_login(body: GoogleLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    if not is_configured(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "Finish first-time setup first.")
    try:
        identity = verify_google_credential(body.credential, get_setting(db, "google_client_id"))
    except GoogleAuthError:
        audit(db, "anonymous", "login_failed", reason="invalid_google_token")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google sign-in could not be verified.")

    if identity.email != str(get_setting(db, "allowed_email")).lower():
        audit(db, "anonymous", "login_denied", email=identity.email)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This Google account is not allowed to use this NiveshMitra.")

    user = db.scalar(select(User).where(User.google_sub == identity.sub))
    if user is None:
        if db.scalar(select(User.id).limit(1)) is not None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "A different Google account is already registered.")
        user = User(google_sub=identity.sub, email=identity.email, display_name=identity.name)
        db.add(user)
        db.flush()

    token = create_pending_session(db, user, request.headers.get("user-agent"))
    db.commit()
    _set_cookie(response, PENDING_COOKIE, token, get_config().pending_login_minutes * 60)
    return {"next": "totp" if user.totp_enabled else "totp_setup"}


@router.get("/totp/setup")
def totp_setup(request: Request, db: Session = Depends(get_db)):
    user, _ = _pending_user(request, db)
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Authenticator app is already set up.")
    if not user.totp_secret_enc:
        user.totp_secret_enc = encrypt(totp.new_totp_secret())
        db.commit()
    secret = decrypt(user.totp_secret_enc)
    uri = totp.provisioning_uri(secret, user.email)
    return {"qr_svg": totp.qr_svg(uri), "manual_key": secret}


@router.post("/totp")
def totp_verify(body: TotpCode, request: Request, response: Response, db: Session = Depends(get_db)):
    user, pending = _pending_user(request, db)
    if not user.totp_secret_enc or not totp.verify_code(decrypt(user.totp_secret_enc), body.code):
        pending.failed_attempts += 1
        if pending.failed_attempts >= MAX_TOTP_ATTEMPTS:
            revoke(db, pending)
        audit(db, user.email, "totp_failed", attempts=pending.failed_attempts)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code didn't match. Check your authenticator app.")

    first_time = not user.totp_enabled
    user.totp_enabled = True
    user.last_login_at = utcnow()
    revoke(db, pending)
    token = create_web_session(db, user, request.headers.get("user-agent"))
    audit(db, user.email, "login", first_totp_setup=first_time)
    db.commit()
    response.delete_cookie(PENDING_COOKIE, path="/")
    _set_cookie(response, COOKIE_NAME, token, get_config().session_days * 86400)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    row = find_session(db, request.cookies.get(COOKIE_NAME), "web")
    if row is not None:
        revoke(db, row)
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email, "name": user.display_name, "language": user.language}
