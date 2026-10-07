import pytest

from app.connectors import trendlyne
from app.connectors.trendlyne import ToolInfo, TrendlyneUnavailable
from app.services import trendlyne_service
from tests.conftest import CSRF

URL = "https://mcp.trendlyne.com/mcp/?token=abcdef0123456789abcdef0123456789abcdef01"


def test_token_is_redacted_from_errors():
    assert "abcdef0123" not in trendlyne.redact(f"ConnectError: failed to reach {URL}")
    assert "token=***" in trendlyne.redact(URL)


def test_nested_exception_groups_are_unpacked(monkeypatch):
    async def boom(url, fn):
        raise ExceptionGroup("outer", [ExceptionGroup("inner", [ConnectionError(f"refused for {URL}")])])

    monkeypatch.setattr(trendlyne, "_session_run", boom)
    with pytest.raises(TrendlyneUnavailable) as e:
        trendlyne.list_tools(URL)
    assert "ConnectionError: refused" in str(e.value) and "abcdef0123" not in str(e.value)


def test_forbidden_token_message(monkeypatch):
    async def boom(url, fn):
        raise RuntimeError('HTTP 403 {"code": 1007}')

    monkeypatch.setattr(trendlyne, "_session_run", boom)
    with pytest.raises(TrendlyneUnavailable, match="refused the token"):
        trendlyne.list_tools(URL)


def test_check_endpoint(signed_in, monkeypatch):
    r = signed_in.post("/api/trading/trendlyne-check", headers=CSRF).json()
    assert r["ok"] is False and "Add your Trendlyne" in r["detail"]

    signed_in.put("/api/settings/secrets/trendlyne_mcp_url", json={"value": URL}, headers=CSRF)
    tools = [ToolInfo(n, "x", []) for n in trendlyne_service.EXPECTED_TOOLS]
    monkeypatch.setattr(trendlyne, "list_tools", lambda url: tools)
    monkeypatch.setattr(trendlyne, "call_tool", lambda url, name, args: {"result": "RELIANCE | 500325"})
    r = signed_in.post("/api/trading/trendlyne-check?sample=true", headers=CSRF).json()
    assert r["ok"] and r["sample"]["ok"] and len(r["tools"]) == 4
    assert "abcdef0123" not in str(r)
