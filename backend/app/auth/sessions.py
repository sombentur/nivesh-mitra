"""Server-side sessions. The browser holds a random token in an HttpOnly cookie; the DB holds only its hash."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_config
from app.db.base import utcnow
from app.db.models import AuthSession, User
from app.security.crypto import hash_token, new_token

COOKIE_NAME = "nm_session"
MAX_TOTP_ATTEMPTS = 5


def create_session(db: Session, user: User, kind: str, lifetime: timedelta, user_agent: str | None) -> str:
    token = new_token()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            kind=kind,
            expires_at=utcnow() + lifetime,
            user_agent=(user_agent or "")[:300],
        )
    )
    return token


def create_pending_session(db: Session, user: User, user_agent: str | None) -> str:
    return create_session(db, user, "pending_2fa", timedelta(minutes=get_config().pending_login_minutes), user_agent)


def create_web_session(db: Session, user: User, user_agent: str | None) -> str:
    return create_session(db, user, "web", timedelta(days=get_config().session_days), user_agent)


def find_session(db: Session, token: str | None, kind: str) -> AuthSession | None:
    if not token:
        return None
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if row is None or row.kind != kind or row.revoked_at is not None or row.expires_at <= utcnow():
        return None
    return row


def revoke(db: Session, row: AuthSession) -> None:
    row.revoked_at = utcnow()
    db.add(row)
