"""Trendlyne MCP connection check. Tool listing is free; the optional sample lookup uses one call of your plan."""

from sqlalchemy.orm import Session

from app.connectors import trendlyne
from app.security.secrets_store import get_secret

EXPECTED_TOOLS = {"search_entities", "get_stock_parameter_values", "get_overview_news_corp_events", "get_ownership_deals_insider_sast"}


def url(db: Session) -> str:
    u = (get_secret(db, "trendlyne_mcp_url") or "").strip()
    if not u:
        raise trendlyne.TrendlyneUnavailable("Add your Trendlyne MCP server URL in Settings first.")
    return u


def diagnose(db: Session, sample: bool = False) -> dict:
    try:
        tools = trendlyne.list_tools(url(db))
    except trendlyne.TrendlyneUnavailable as exc:
        return {"ok": False, "detail": str(exc), "tools": [], "sample": None}
    names = {t.name for t in tools}
    missing = sorted(EXPECTED_TOOLS - names)
    out = {
        "ok": not missing,
        "detail": f"Connected — {len(tools)} tools available" + (f"; missing {', '.join(missing)}" if missing else ""),
        "tools": [{"name": t.name, "description": t.description} for t in tools],
        "sample": None,
    }
    if sample:
        try:
            r = trendlyne.call_tool(url(db), "search_entities", {"query": "Reliance Industries", "entity_type": "stock", "limit": 1})
            text = r.get("result", "") if isinstance(r, dict) else str(r)
            out["sample"] = {"ok": "RELIANCE" in text, "detail": "Looked up Reliance Industries (used 1 call)" if "RELIANCE" in text else text[:200]}
        except trendlyne.TrendlyneUnavailable as exc:
            out["sample"] = {"ok": False, "detail": str(exc)}
    return out
