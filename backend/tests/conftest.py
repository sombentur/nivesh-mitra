import os
import tempfile

# Must be set before any app module is imported (config and engine are created at import time).
_TMP = tempfile.mkdtemp(prefix="nm-test-")
os.environ["NM_DATA_DIR"] = _TMP
os.environ["NM_MASTER_KEY_OVERRIDE"] = "4rhr4Sa0d25OB5NM7rlCspX7TWqr4tvaJjwxiaeAmQI="  # dummy key for tests only
os.environ["NM_SCHEDULER_ENABLED"] = "false"

import pyotp  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.auth import router as auth_router  # noqa: E402
from app.auth.google import GoogleIdentity  # noqa: E402
from app.db.base import Base, SessionLocal  # noqa: E402
from app.db.migrate import upgrade_to_head  # noqa: E402
from app.main import app  # noqa: E402

CSRF = {"X-NM-CSRF": "1"}
TEST_CLIENT_ID = "1234567890-abcdefghij.apps.googleusercontent.com"
TEST_EMAIL = "owner@example.com"

upgrade_to_head()


@pytest.fixture(autouse=True)
def clean_db():
    yield
    with SessionLocal() as db:
        # Tests may wipe append-only tables: lift the triggers for the cleanup, then put them back.
        triggers = db.execute(text("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'")).all()
        for name, _ in triggers:
            db.execute(text(f"DROP TRIGGER {name}"))
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        for _, sql in triggers:
            db.execute(text(sql))
        db.commit()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def signed_in(client, monkeypatch):
    """A client that has completed setup, Google sign-in and the authenticator step."""
    client.post("/api/setup", json={"google_client_id": TEST_CLIENT_ID, "allowed_email": TEST_EMAIL}, headers=CSRF)
    monkeypatch.setattr(
        auth_router,
        "verify_google_credential",
        lambda c, cid: GoogleIdentity(sub="sub-1", email=TEST_EMAIL, name="Test Owner"),
    )
    client.post("/api/auth/google", json={"credential": "ok"}, headers=CSRF)
    secret = client.get("/api/auth/totp/setup").json()["manual_key"]
    r = client.post("/api/auth/totp", json={"code": pyotp.TOTP(secret).now()}, headers=CSRF)
    assert r.status_code == 200
    return client
