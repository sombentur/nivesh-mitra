from app.db.base import SessionLocal
from app.db.models import AuditLog, Secret
from app.security.secrets_store import get_secret
from tests.conftest import CSRF

FAKE_KEY = "sk-test-not-a-real-key-9876"


def test_settings_require_login(client):
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/settings/secrets").status_code == 401


def test_settings_defaults_and_validation(signed_in):
    client = signed_in
    s = client.get("/api/settings").json()
    assert s["explanation_mode"] == "template"
    assert s["fundamentals_provider"] == "manual"
    assert "google_client_id" not in s
    assert "paper_mode_start" not in s  # system-managed, not user-editable

    r = client.patch("/api/settings", json={"explanation_mode": "claude"}, headers=CSRF)
    assert r.json()["explanation_mode"] == "claude"
    assert client.patch("/api/settings", json={"explanation_mode": "gpt"}, headers=CSRF).status_code == 400
    assert client.patch("/api/settings", json={"allowed_email": "x@y.com"}, headers=CSRF).status_code == 400
    assert client.patch("/api/settings", json={"sebi_ack_at": "2026-01-01"}, headers=CSRF).status_code == 400


def test_secret_is_encrypted_and_never_returned(signed_in):
    client = signed_in
    r = client.put("/api/settings/secrets/anthropic_api_key", json={"value": FAKE_KEY}, headers=CSRF)
    assert r.status_code == 200

    listing = client.get("/api/settings/secrets")
    assert FAKE_KEY not in listing.text
    entry = next(s for s in listing.json() if s["name"] == "anthropic_api_key")
    assert entry["is_set"] and entry["last4"] == "9876"

    with SessionLocal() as db:
        assert FAKE_KEY not in db.get(Secret, "anthropic_api_key").ciphertext
        assert get_secret(db, "anthropic_api_key") == FAKE_KEY
        audit_text = str([a.detail_json for a in db.query(AuditLog).all()])
        assert FAKE_KEY not in audit_text

    assert client.put("/api/settings/secrets/unknown", json={"value": "x"}, headers=CSRF).status_code == 404
    client.delete("/api/settings/secrets/anthropic_api_key", headers=CSRF)
    entry = next(s for s in client.get("/api/settings/secrets").json() if s["name"] == "anthropic_api_key")
    assert entry["is_set"] is False
