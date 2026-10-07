from datetime import timedelta

from app.db.base import SessionLocal, utcnow
from app.engines.plan import months_until
from app.engines.profile import future_value
from app.db.models import AllocationTarget, StrategyVersion
from app.services import profile as profile_svc
from tests.conftest import CSRF

ANSWERS = dict(
    age=34,
    income_range="1lto2l",
    monthly_expenses=40000,
    monthly_investable=25000,
    emergency_savings=100000,  # 2.5 months → trading locked
    monthly_emi=15000,
    horizon="5plus",
    fall_reaction="hold",
    experience="none",
)


def _submit(client, **kw):
    r = client.post("/api/profile", json={**ANSWERS, **kw}, headers=CSRF)
    assert r.status_code == 200, r.text
    return r.json()


def test_profile_endpoints_require_login(client):
    assert client.get("/api/profile/rules").status_code == 401
    assert client.post("/api/profile", json=ANSWERS, headers=CSRF).status_code == 401


def test_submit_profile_and_view(signed_in):
    v = _submit(signed_in)
    assert v["result"]["final_category"] == "moderate"
    assert v["allocation"]["target"] == {"core": 75, "satellite": 20, "trading": 5}
    # emergency fund < 3 months and paper trading not done → trading locked, its share stays in core
    assert v["allocation"]["trading_locked"] is True
    assert v["allocation"]["effective"] == {"core": 80, "satellite": 20, "trading": 0}
    assert len(v["allocation"]["trading_lock_reasons"]) == 2
    assert v["result"]["emergency"]["status"] == "building"
    assert signed_in.get("/api/profile").json()["id"] == v["id"]
    with SessionLocal() as db:
        assert db.query(StrategyVersion).filter_by(engine="profile").count() == 1


def test_rerun_keeps_history(signed_in):
    _submit(signed_in)
    v2 = _submit(signed_in, horizon="lt1")
    assert v2["result"]["final_category"] == "conservative"
    hist = signed_in.get("/api/profile/history").json()
    assert [h["is_current"] for h in hist] == [True, False]


def test_invalid_answers(signed_in):
    assert signed_in.post("/api/profile", json={**ANSWERS, "age": 12}, headers=CSRF).status_code == 422
    assert signed_in.post("/api/profile", json={**ANSWERS, "horizon": "never"}, headers=CSRF).status_code == 400


def test_tightening_is_immediate(signed_in):
    _submit(signed_in)
    r = signed_in.put("/api/profile/allocation", json={"core": 80, "satellite": 20, "trading": 0}, headers=CSRF)
    a = r.json()["allocation"]
    assert a["target"]["trading"] == 0 and a["pending"] is None and a["is_user_override"] is True


def test_raising_trading_needs_reason_and_waits_24h(signed_in, monkeypatch):
    _submit(signed_in)
    body = {"core": 70, "satellite": 20, "trading": 10}
    r = signed_in.put("/api/profile/allocation", json=body, headers=CSRF)
    assert r.status_code == 400 and "reason" in r.json()["detail"]

    r = signed_in.put("/api/profile/allocation", json={**body, "reason": "I want to learn trading"}, headers=CSRF)
    a = r.json()["allocation"]
    assert a["target"]["trading"] == 5  # unchanged for now
    assert a["pending"]["trading"] == 10

    # a second raise replaces the first waiting change rather than stacking
    signed_in.put("/api/profile/allocation", json={"core": 68, "satellite": 20, "trading": 12, "reason": "Changed my mind again"}, headers=CSRF)
    with SessionLocal() as db:
        assert db.query(AllocationTarget).filter(AllocationTarget.effective_at > utcnow()).count() == 1

    # 25 hours later the waiting change is in effect, with a warning above 10%
    later = utcnow() + timedelta(hours=25)
    monkeypatch.setattr(profile_svc, "utcnow", lambda: later)
    a = signed_in.get("/api/profile").json()["allocation"]
    assert a["target"] == {"core": 68, "satellite": 20, "trading": 12}
    assert a["pending"] is None
    assert any("safe limit" in w for w in a["warnings"])


def test_cancel_pending(signed_in):
    _submit(signed_in)
    signed_in.put("/api/profile/allocation", json={"core": 70, "satellite": 20, "trading": 10, "reason": "Testing the delay"}, headers=CSRF)
    a = signed_in.delete("/api/profile/allocation/pending", headers=CSRF).json()["allocation"]
    assert a["pending"] is None and a["target"]["trading"] == 5


def test_trading_hard_ceiling_and_sum(signed_in):
    _submit(signed_in)
    r = signed_in.put("/api/profile/allocation", json={"core": 55, "satellite": 20, "trading": 25, "reason": "Too much trading"}, headers=CSRF)
    assert r.status_code == 400 and "20%" in r.json()["detail"]
    r = signed_in.put("/api/profile/allocation", json={"core": 50, "satellite": 20, "trading": 5}, headers=CSRF)
    assert r.status_code == 400 and "100%" in r.json()["detail"]
    check = signed_in.post("/api/profile/split-check", json={"core": 45, "satellite": 40, "trading": 15}, headers=CSRF).json()
    assert check["ok"] and len(check["warnings"]) == 3


def test_onboarding_flow(signed_in):
    s = signed_in.get("/api/onboarding/status").json()
    assert s == {"profile_done": False, "sebi_acknowledged": False, "paper_started": False, "complete": False}
    _submit(signed_in)
    assert signed_in.post("/api/onboarding/complete", headers=CSRF).status_code == 409
    signed_in.post("/api/onboarding/sebi-ack", headers=CSRF)
    s = signed_in.post("/api/onboarding/complete", headers=CSRF).json()
    assert s["complete"] is True
    paper = signed_in.get("/api/profile").json()["paper"]
    assert paper["started_on"] == utcnow().date().isoformat() and paper["days_left"] == 60


def test_goals_crud(signed_in):
    this_year = utcnow().year
    body = {"name": "Riya's college", "goal_type": "child_education", "target_amount_today": 2000000, "target_year": this_year + 10}
    g = signed_in.post("/api/goals", json=body, headers=CSRF).json()
    months = months_until(this_year + 10, utcnow().date())  # to the middle (July) of the goal year
    assert g["inflation_rate"] == 0.08 and g["years_away"] == round(months / 12, 1)
    assert g["target_amount_future"] == future_value(2000000, 0.08, months / 12)

    r = signed_in.post("/api/goals", json={**body, "target_year": this_year - 1}, headers=CSRF)
    assert r.status_code == 422
    assert signed_in.post("/api/goals", json={**body, "goal_type": "yacht"}, headers=CSRF).status_code == 400

    signed_in.put(f"/api/goals/{g['id']}", json={**body, "target_amount_today": 2500000, "inflation_rate": 0.1}, headers=CSRF)
    assert signed_in.get("/api/goals").json()[0]["inflation_rate"] == 0.1
    signed_in.delete(f"/api/goals/{g['id']}", headers=CSRF)
    assert signed_in.get("/api/goals").json() == []
