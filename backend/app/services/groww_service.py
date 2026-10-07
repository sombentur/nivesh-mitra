"""Builds the read-only Groww client from your encrypted keys, reusing one login across calls."""

import hashlib
import threading
from datetime import timedelta

from sqlalchemy.orm import Session

from app.connectors.groww import GrowwNoDataAccess, GrowwNotConnected, GrowwReadOnlyClient
from app.connectors.http import SourceUnavailable
from app.db.base import utcnow
from app.security.secrets_store import get_secret

_lock = threading.Lock()
_cached: tuple[str, GrowwReadOnlyClient] | None = None


def client(db: Session) -> GrowwReadOnlyClient:
    global _cached
    token, secret = get_secret(db, "groww_totp_token"), get_secret(db, "groww_totp_secret")
    if not token or not secret:
        raise GrowwNotConnected("Add your Groww API key and secret (or TOTP secret) in Settings first.")
    fingerprint = hashlib.sha256(f"{token}|{secret}".encode()).hexdigest()
    with _lock:
        if _cached is None or _cached[0] != fingerprint:  # keys changed → new client
            _cached = (fingerprint, GrowwReadOnlyClient(token, secret))
        return _cached[1]


def _check(fn) -> dict:
    try:
        return {"ok": True, "detail": fn()}
    except GrowwNoDataAccess as exc:
        return {"ok": False, "detail": str(exc)}
    except SourceUnavailable as exc:
        return {"ok": False, "detail": str(exc)}


def diagnose(db: Session) -> dict:
    """Log in, then try each kind of read-only access separately. Returns only non-sensitive facts."""
    c = client(db)
    login = _check(lambda: c.profile().get("active_segments") or [])
    if not login["ok"]:
        return {"auth_method": c.auth_method, "login": login, "portfolio": None, "prices": None, "history": None}
    today = utcnow().date()
    return {
        "auth_method": c.auth_method,
        "login": {"ok": True, "detail": f"Logged in (segments: {', '.join(login['detail']) or 'none'})"},
        "portfolio": _check(lambda: f"{len(c.holdings())} holdings visible"),
        "prices": _check(lambda: f"Nifty 50 at {c.ltp(['NSE_NIFTY']).get('NSE_NIFTY', 'n/a')}"),
        "history": _check(lambda: f"{len(c.daily_candles('NSE-NIFTY', today - timedelta(days=14), today))} daily candles for the last 2 weeks"),
    }
