import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.db.base import SessionLocal
from app.db.models import IndexDaily, NewsBrief
from app.security.secrets_store import set_secret
from app.services import app_settings, claude_client, market, news

HEADER = (
    "NSEcode | BSEcode | ISIN | NSENumber | BSEScriptCode | stockName | stockId | pageType | userType | insight | postType | "
    "postTypeNumber | related | currentPrice | dayChangeP | pubDate | title | description | descriptionHTML | postId | authorId | "
    "isPremium | url | source | videoUrl | pdfUrl | imageUrl | audioUrl"
)


def row(sym, title, desc, when, post_id, url="https://example.com/a", kind="News"):
    return (
        f"  {sym} | 500325 | INE0 | 1 | {sym} | {sym.title()} Ltd. | 1 | Equity | 32 | {{}} | {kind} | 1 | None | 100.0 | -1.0 | "
        f"{when} | {title} | {desc} | {desc} | {post_id} | 1 | False | {url} | Business Line |  | None | None | None"
    )


def table(*rows):
    return "newsList:\n  " + HEADER + "\n" + "\n".join(rows) + "\n"


def iso(hours_ago):
    return (datetime.now(news.IST) - timedelta(hours=hours_ago)).isoformat()


def test_parse_handles_pipes_inside_descriptions():
    text = table(row("RELIANCE", "Rosatom in talks with RIL", "Nuclear | power push", iso(2), "11"), row("RELIANCE", "Old", "x", iso(100), "12", url="javascript:x"))
    items = news.parse_news(text)
    assert [i["title"] for i in items] == ["Rosatom in talks with RIL", "Old"]
    assert items[0]["description"] == "Nuclear" and items[0]["source"] == "Business Line" and items[0]["url"] == "https://example.com/a"
    assert items[1]["url"] is None  # only web links are kept
    assert news.parse_news("no table here") == []


@pytest.fixture
def trendlyne_on(monkeypatch):
    with SessionLocal() as db:
        app_settings.set_setting(db, "trendlyne_enabled", True)
        set_secret(db, "trendlyne_mcp_url", "https://mcp.example/abc")
        db.commit()
    feeds = {
        "RELIANCE": table(row("RELIANCE", "RIL wins big order", "Order win", iso(3), "1"), row("RELIANCE", "Trading window closure", "Routine", iso(5), "2"), row("RELIANCE", "Stale", "old", iso(80), "3")),
        "INFY": table(row("INFY", "Infosys cuts guidance", "Weak demand", iso(4), "4")),
    }
    monkeypatch.setattr(news.trendlyne, "call_tool", lambda url, name, args: {"result": feeds.get(args["stock_code"], "newsList:\n")})
    monkeypatch.setattr(news, "HEAVYWEIGHTS", ["RELIANCE", "INFY"])
    monkeypatch.setattr(market, "snapshot", lambda db: {"lists": {"gainers": [], "losers": []}, "stocks": {}, "breadth": {"advancers": 10, "decliners": 20}})
    monkeypatch.setattr(news.dashboard, "market", lambda db: {"mood": "Weak", "reason": "Nifty below its averages."})
    yield


def test_refresh_with_claude_tags_and_scores(trendlyne_on, monkeypatch):
    seen = {}

    def fake_call(db, *, system, user, schema, **kw):
        seen["payload"] = json.loads(user)
        return {
            "tags": [{"id": 0, "tone": "positive", "why": "A large order adds revenue."}, {"id": 1, "tone": "neutral", "why": "Routine filing."}, {"id": 2, "tone": "negative", "why": "Lower growth expected."}],
            "brief_en": "Mixed company news while the market trend is weak.",
            "brief_kn": "ಕನ್ನಡ ಸಾರಾಂಶ",
        }

    monkeypatch.setattr(news.claude_client, "json_call", fake_call)
    with SessionLocal() as db:
        app_settings.set_setting(db, "language", "kn")
        db.commit()
        msg = news.refresh(db)
        assert "3 headlines from 2 companies" in msg and "tone mixed" in msg
        assert [h["title"] for h in seen["payload"]["headlines"]] == ["RIL wins big order", "Trading window closure", "Infosys cuts guidance"]  # stale news left out
        assert seen["payload"]["market"]["market_mood"] == "Weak"
        p = news.cached()
        assert p["source"] == "claude" and p["counts"] == {"positive": 1, "negative": 1, "neutral": 1} and p["brief_kn"] == "ಕನ್ನಡ ಸಾರಾಂಶ"
        assert {i["title"]: i["tone"] for i in p["items"]}["Infosys cuts guidance"] == "negative"
        b = db.query(NewsBrief).one()
        assert b.overall == "mixed" and b.headlines == 3 and b.source == "claude"


def test_refresh_falls_back_to_template_without_claude(trendlyne_on, monkeypatch):
    def refuse(*a, **k):
        raise claude_client.ClaudeUnavailable("Explanations are set to templates in Settings")

    monkeypatch.setattr(news.claude_client, "json_call", refuse)
    with SessionLocal() as db:
        msg = news.refresh(db)
        p = news.cached()
    assert "template" in msg and p["overall"] == "unrated" and p["brief_kn"] is None
    assert "3 headlines from 2 companies" in p["brief_en"] and all("tone" not in i for i in p["items"])


def test_cache_is_deleted_after_24_hours(trendlyne_on, monkeypatch):
    monkeypatch.setattr(news.claude_client, "json_call", lambda *a, **k: (_ for _ in ()).throw(claude_client.ClaudeUnavailable("off")))
    with SessionLocal() as db:
        news.refresh(db)
    path = news._cache_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["fetched_at"] = (datetime.now(news.IST) - timedelta(hours=25)).isoformat()
    path.write_text(json.dumps(data), encoding="utf-8")
    assert news.cached() is None and not path.exists()


def test_scorecard_counts_agreement_with_the_nifty():
    with SessionLocal() as db:
        for d, c in [(date(2026, 9, 21), 100.0), (date(2026, 9, 22), 101.0), (date(2026, 9, 23), 100.0), (date(2026, 9, 24), 99.0)]:
            db.add(IndexDaily(symbol="NIFTY", date=d, open=c, high=c, low=c, close=c))
        for d, tone in [(date(2026, 9, 22), "positive"), (date(2026, 9, 23), "positive"), (date(2026, 9, 24), "negative"), (date(2026, 9, 24), "positive")]:
            db.add(NewsBrief(session_date=d, overall=tone, headlines=5, source="claude"))
        db.commit()
        s = news.scorecard(db)
    assert s == {"days": 3, "agreed": 2, "min_days": 20}  # 22nd up ✓, 23rd down ✗, 24th: the first brief (negative) ✓


def test_session_for():
    ist = news.IST
    assert news.session_for(datetime(2026, 9, 30, 8, 40, tzinfo=ist)) == date(2026, 9, 30)
    assert news.session_for(datetime(2026, 9, 30, 15, 45, tzinfo=ist)) == date(2026, 10, 1)
    assert news.session_for(datetime(2026, 10, 2, 16, 0, tzinfo=ist)) == date(2026, 10, 5)  # Friday evening → Monday


def test_news_api(signed_in, monkeypatch):
    from app import scheduler
    from tests.conftest import CSRF

    started = []
    monkeypatch.setattr(scheduler, "run_job_async", lambda name, trigger="manual": started.append(name) or True)
    r = signed_in.get("/api/news").json()
    assert r["pulse"] is None and r["scorecard"]["days"] == 0 and r["refreshing"] is False
    assert signed_in.post("/api/news/refresh", headers=CSRF).json() == {"started": True} and started == ["news_pulse"]


def test_claude_spend_is_tracked_and_capped(monkeypatch):
    calls = []

    class FakeMessages:
        def create(self, **kw):
            calls.append(kw)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text='{"ok": true}')],
                usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0),
            )

    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kw: SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages())))
    with SessionLocal() as db:
        with pytest.raises(claude_client.ClaudeUnavailable, match="templates"):
            claude_client.json_call(db, system="s", user="u", schema={})
        app_settings.set_setting(db, "explanation_mode", "claude")
        set_secret(db, "anthropic_api_key", "sk-ant-test")
        app_settings.set_setting(db, "claude_monthly_cap_inr", 500)
        db.commit()
        assert claude_client.json_call(db, system="s", user="u", schema={"type": "object"}) == {"ok": True}
        assert calls[0]["model"] == "claude-opus-5-5" and calls[0]["fallbacks"] == "default" and calls[0]["output_config"]["effort"] == "low"
        s = claude_client.spend(db)
        assert s["calls"] == 1 and s["inr"] == pytest.approx(4.0 * claude_client.USD_TO_INR)  # 1M input tokens at $4
        claude_client.json_call(db, system="s", user="u", schema={})  # ₹352 + ₹352 goes past the ₹500 cap…
        with pytest.raises(claude_client.ClaudeUnavailable, match="budget"):  # …so the next call is refused
            claude_client.json_call(db, system="s", user="u", schema={})


def test_workspace_id_is_sent_and_workspace_errors_are_explained(monkeypatch):
    import anthropic
    import httpx2

    made = []

    class Reject:
        def create(self, **kw):
            req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
            body = {"type": "error", "error": {"type": "invalid_request_error", "message": "This API key is not scoped to a workspace, so this request must include the anthropic-workspace-id header"}}
            raise anthropic.BadRequestError("Error code: 400", response=httpx2.Response(400, request=req, json=body), body=body)

    monkeypatch.setattr(claude_client.anthropic, "Anthropic", lambda **kw: made.append(kw) or SimpleNamespace(beta=SimpleNamespace(messages=Reject())))
    with SessionLocal() as db:
        app_settings.set_setting(db, "explanation_mode", "claude")
        set_secret(db, "anthropic_api_key", "sk-ant-test")
        db.commit()
        with pytest.raises(claude_client.ClaudeUnavailable, match="workspace ID in Settings"):
            claude_client.json_call(db, system="s", user="u", schema={})
        assert made[-1]["default_headers"] is None
        set_secret(db, "anthropic_workspace_id", "wrkspc_123")
        db.commit()
        with pytest.raises(claude_client.ClaudeUnavailable):
            claude_client.json_call(db, system="s", user="u", schema={})
        assert made[-1]["default_headers"] == {"anthropic-workspace-id": "wrkspc_123"}
