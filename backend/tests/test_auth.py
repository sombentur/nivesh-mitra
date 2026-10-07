import pyotp
import pytest

from app.auth import router as auth_router
from app.auth.google import GoogleAuthError, GoogleIdentity
from app.db.base import SessionLocal
from app.db.models import AuditLog, User
from app.security.crypto import decrypt
from tests.conftest import CSRF

CLIENT_ID = "1234567890-abcdefghij.apps.googleusercontent.com"
EMAIL = "owner@example.com"


def _configure(client):
    r = client.post("/api/setup", json={"google_client_id": CLIENT_ID, "allowed_email": EMAIL}, headers=CSRF)
    assert r.status_code == 200


@pytest.fixture
def google_as(monkeypatch):
    def _as(email: str, sub: str = "google-sub-1"):
        def fake_verify(credential, client_id):
            assert client_id == CLIENT_ID
            if credential == "bad":
                raise GoogleAuthError("bad token")
            return GoogleIdentity(sub=sub, email=email, name="Owner")

        monkeypatch.setattr(auth_router, "verify_google_credential", fake_verify)

    return _as


def _login(client) -> str:
    """Full first login; returns the TOTP secret."""
    r = client.post("/api/auth/google", json={"credential": "ok"}, headers=CSRF)
    assert r.json() == {"next": "totp_setup"}
    setup = client.get("/api/auth/totp/setup").json()
    assert "<svg" in setup["qr_svg"]
    secret = setup["manual_key"]
    r = client.post("/api/auth/totp", json={"code": pyotp.TOTP(secret).now()}, headers=CSRF)
    assert r.status_code == 200
    return secret


def test_health(client):
    assert client.get("/api/health").json()["decision_only"] is True


def test_writes_need_csrf_header(client):
    r = client.post("/api/setup", json={"google_client_id": CLIENT_ID, "allowed_email": EMAIL})
    assert r.status_code == 403


def test_setup_validates_and_locks_after_first_login(client, google_as):
    r = client.post("/api/setup", json={"google_client_id": "nope", "allowed_email": EMAIL}, headers=CSRF)
    assert r.status_code == 422
    assert client.get("/api/setup/status").json()["configured"] is False

    _configure(client)
    assert client.get("/api/setup/status").json() == {
        "configured": True,
        "locked": False,
        "google_client_id": CLIENT_ID,
    }
    google_as(EMAIL)
    _login(client)
    assert client.get("/api/setup/status").json()["locked"] is True
    r = client.post("/api/setup", json={"google_client_id": CLIENT_ID, "allowed_email": "x@y.com"}, headers=CSRF)
    assert r.status_code == 409


def test_full_login_and_logout(client, google_as):
    _configure(client)
    google_as(EMAIL)
    assert client.get("/api/auth/me").status_code == 401
    secret = _login(client)
    assert client.get("/api/auth/me").json()["email"] == EMAIL

    # TOTP secret is stored encrypted, never in plain text
    with SessionLocal() as db:
        user = db.query(User).one()
        assert user.totp_enabled
        assert secret not in user.totp_secret_enc
        assert decrypt(user.totp_secret_enc) == secret

    client.post("/api/auth/logout", headers=CSRF)
    assert client.get("/api/auth/me").status_code == 401

    # Second login goes straight to the code prompt
    r = client.post("/api/auth/google", json={"credential": "ok"}, headers=CSRF)
    assert r.json() == {"next": "totp"}
    assert client.get("/api/auth/totp/setup").status_code == 409


def test_other_google_account_is_refused(client, google_as):
    _configure(client)
    google_as("stranger@example.com")
    r = client.post("/api/auth/google", json={"credential": "ok"}, headers=CSRF)
    assert r.status_code == 403
    with SessionLocal() as db:
        assert db.query(User).count() == 0
        assert db.query(AuditLog).filter_by(action="login_denied").count() == 1


def test_invalid_google_token(client, google_as):
    _configure(client)
    google_as(EMAIL)
    assert client.post("/api/auth/google", json={"credential": "bad"}, headers=CSRF).status_code == 401


def test_totp_locks_after_five_wrong_codes(client, google_as):
    _configure(client)
    google_as(EMAIL)
    client.post("/api/auth/google", json={"credential": "ok"}, headers=CSRF)
    client.get("/api/auth/totp/setup")
    for _ in range(5):
        r = client.post("/api/auth/totp", json={"code": "000000"}, headers=CSRF)
        assert r.status_code == 401
    # pending login is now revoked — even a correct code must start over
    r = client.get("/api/auth/totp/setup")
    assert r.status_code == 401
