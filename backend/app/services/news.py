"""News pulse: recent headlines for the market's heavyweights and today's biggest movers (Trendlyne), tagged by Claude.

Honesty rules
- Headlines are shown as published, with their source and link. Claude only labels tone and summarises the headlines
  it is given; it never predicts prices or tells you to buy or sell.
- News is not a forecast. Each brief's overall tone is recorded (just the label and counts) next to how the Nifty 50
  actually moved that session, so the app can show how often the two agreed.
- Trendlyne's terms allow keeping its data for up to 24 hours: the headline cache is deleted after that.
"""

import json
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_config
from app.connectors import trendlyne
from app.db.base import utcnow
from app.db.models import IndexDaily, NewsBrief
from app.engines import holidays
from app.services import app_settings, claude_client, dashboard, market, trendlyne_service
from app.services.errors import JobSkipped

Progress = Callable[[int, int], None]
IST = ZoneInfo("Asia/Kolkata")
HEAVYWEIGHTS = ["HDFCBANK", "RELIANCE", "ICICIBANK", "INFY", "BHARTIARTL", "TCS", "LT", "ITC", "SBIN", "AXISBANK"]
MOVERS_EACH_SIDE = 3
PER_STOCK = 3
RECENT_HOURS = 48
CACHE_HOURS = 24
TONES = ("positive", "negative", "neutral")
HEAD = 17  # columns before the free-text description in Trendlyne's news table (NSEcode … title)
TAIL = 9  # columns after it (postId … audioUrl)


def _noop(_d: int, _t: int) -> None:
    pass


def _cache_path() -> Path:
    d = get_config().data_dir / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / "news.json"


def cached() -> dict | None:
    """The last news pulse if it's under 24 hours old (older copies are deleted: Trendlyne's 24-hour rule)."""
    p = _cache_path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if datetime.fromisoformat(data["fetched_at"]) > datetime.now(IST) - timedelta(hours=CACHE_HOURS):
            return data
    except (ValueError, KeyError):
        pass
    p.unlink(missing_ok=True)
    return None


def parse_news(text: str) -> list[dict]:
    """Trendlyne returns a pipe-separated table under 'newsList:'. Descriptions may contain pipes, so the fixed columns
    are read from both ends of each row."""
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if "NSEcode" in ln and "title" in ln)
    except StopIteration:
        return []
    header = [h.strip() for h in lines[start].split(" | ")]
    out = []
    for ln in lines[start + 1 :]:
        if " | " not in ln:
            break
        parts = [p.strip() for p in ln.split(" | ")]
        if len(header) < HEAD + TAIL or len(parts) < HEAD + TAIL:
            continue
        row = dict(zip(header[:HEAD], parts[:HEAD])) | dict(zip(header[-TAIL:], parts[-TAIL:]))
        description = parts[HEAD] if len(parts) > HEAD + TAIL else ""
        try:
            published = datetime.fromisoformat(row.get("pubDate", "").replace("Z", "+00:00"))
        except ValueError:
            continue
        url = row.get("url", "")
        out.append(
            {
                "symbol": row.get("NSEcode") or "",
                "company": row.get("stockName") or "",
                "kind": row.get("postType") or "News",
                "title": row.get("title", "")[:300],
                "description": description[:400],
                "source": row.get("source") or "",
                "url": url if url.startswith(("https://", "http://")) else None,
                "published": published.isoformat(),
                "post_id": row.get("postId") or row.get("title", "")[:80],
            }
        )
    return out


def _gather(db: Session, progress: Progress) -> tuple[list[dict], dict[str, str]]:
    snap = market.snapshot(db)
    movers = {s: "gainer" for s in snap["lists"]["gainers"][:MOVERS_EACH_SIDE]} | {s: "loser" for s in snap["lists"]["losers"][:MOVERS_EACH_SIDE]}
    roles = {s: "heavyweight" for s in HEAVYWEIGHTS} | {s: r for s, r in movers.items() if s not in HEAVYWEIGHTS}
    url = trendlyne_service.url(db)
    cutoff = datetime.now(IST) - timedelta(hours=RECENT_HOURS)
    items, seen = [], set()
    for n, sym in enumerate(roles):
        try:
            r = trendlyne.call_tool(url, "get_overview_news_corp_events", {"stock_code": sym, "type": "news"})
        except trendlyne.TrendlyneUnavailable:
            continue
        text = r.get("result", "") if isinstance(r, dict) else str(r)
        fresh = [x for x in parse_news(text if isinstance(text, str) else json.dumps(text)) if datetime.fromisoformat(x["published"]) >= cutoff]
        for x in sorted(fresh, key=lambda x: x["published"], reverse=True)[:PER_STOCK]:
            if x["post_id"] in seen:
                continue
            seen.add(x["post_id"])
            stock = snap["stocks"].get(sym)
            items.append(x | {"symbol": x["symbol"] or sym, "role": roles[sym], "change_pct": stock["change_pct"] if stock else None})
        progress(n + 1, len(roles))
    return items, roles


SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "tone": {"type": "string", "enum": list(TONES)}, "why": {"type": "string"}},
                "required": ["id", "tone", "why"],
                "additionalProperties": False,
            },
        },
        "brief_en": {"type": "string"},
        "brief_kn": {"type": "string"},
    },
    "required": ["tags", "brief_en", "brief_kn"],
    "additionalProperties": False,
}

SYSTEM = """You help a beginner investor in India make sense of today's stock-market news.

You receive recent headlines (company, source, short description) and a few facts about the market's current trend.
1. For each headline, label its likely effect on that company's share price: positive, negative or neutral, with a
   reason of at most 15 plain words. Routine filings (trading-window closures, meeting dates, compliance letters) are neutral.
2. Write brief_en: at most 80 words on what the news is mostly about and what it may mean, and mention the market trend
   you were given. Then brief_kn: the same brief in simple Kannada.

Rules: use only the information provided. Never predict prices, index levels or percentages, and never tell the reader
to buy or sell. Say "may", not "will". If the headlines are mostly routine, say so plainly."""


def _market_facts(db: Session) -> dict:
    m = dashboard.market(db) or {}
    b = market.snapshot(db)["breadth"]
    return {"market_mood": m.get("mood"), "trend_reason": m.get("reason"), "stocks_up_today": b["advancers"], "stocks_down_today": b["decliners"]}


def _overall(pos: int, neg: int) -> str:
    if pos == neg == 0:
        return "neutral"
    if pos >= 1.5 * max(neg, 1) and pos > neg:
        return "positive"
    if neg >= 1.5 * max(pos, 1) and neg > pos:
        return "negative"
    return "mixed"


def _template_brief(items: list[dict], companies: int, facts: dict) -> str:
    mood = f" The market trend is {facts['market_mood'].lower()}." if facts.get("market_mood") else ""
    return f"{len(items)} headlines from {companies} companies in the last two days.{mood} Read the headlines below; tone labels need Claude explanations switched on in Settings."


def session_for(now: datetime) -> date:
    """The trading session a brief speaks to: today before the 3:30 PM close on a trading day, else the next trading day."""
    d = now.date()
    if holidays.is_trading_day(d) and now.time() < time(15, 30):
        return d
    return holidays.next_trading_day(d)


def refresh(db: Session, progress: Progress = _noop) -> str:
    """Fetch, tag and cache the news pulse (the scheduled job; also run from the dashboard's refresh button)."""
    if not app_settings.get_setting(db, "trendlyne_enabled"):
        raise JobSkipped("Trendlyne is switched off in Settings")
    try:
        items, roles = _gather(db, progress)
    except trendlyne.TrendlyneUnavailable as exc:
        raise JobSkipped(str(exc)) from exc
    facts = _market_facts(db)
    companies = len({x["symbol"] for x in items})
    source, note = "template", None
    brief_en, brief_kn = _template_brief(items, companies, facts), None
    if items:
        try:
            payload = {"market": facts, "headlines": [{"id": i, "company": x["company"], "source": x["source"], "title": x["title"], "description": x["description"]} for i, x in enumerate(items)]}
            reply = claude_client.json_call(db, system=SYSTEM, user=json.dumps(payload, ensure_ascii=False), schema=SCHEMA)
            tags = {t["id"]: t for t in reply["tags"] if t.get("tone") in TONES}
            for i, x in enumerate(items):
                if i in tags:
                    x["tone"], x["why"] = tags[i]["tone"], tags[i]["why"][:160]
            brief_en, brief_kn, source = reply["brief_en"][:900], (reply["brief_kn"] or None), "claude"
        except claude_client.ClaudeUnavailable as exc:
            note = str(exc)
    if app_settings.get_setting(db, "language") != "kn":
        brief_kn = None
    counts = {t: sum(1 for x in items if x.get("tone") == t) for t in TONES}
    overall = _overall(counts["positive"], counts["negative"]) if source == "claude" else "unrated"
    now = datetime.now(IST)
    data = {
        "fetched_at": now.isoformat(timespec="seconds"),
        "session": session_for(now).isoformat(),
        "source": source,
        "note": note,
        "brief_en": brief_en,
        "brief_kn": brief_kn,
        "overall": overall,
        "counts": counts,
        "companies": companies,
        "items": sorted(items, key=lambda x: x["published"], reverse=True),
    }
    tmp = _cache_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_cache_path())
    db.add(NewsBrief(session_date=session_for(now), overall=overall, positive=counts["positive"], negative=counts["negative"], neutral=counts["neutral"], headlines=len(items), source=source))
    db.commit()
    return f"{len(items)} headlines from {companies} companies; tone {overall} ({'Claude' if source == 'claude' else 'template' + (f' — {note}' if note else '')})"


def scorecard(db: Session) -> dict:
    """How often a clearly positive/negative morning tone matched the Nifty 50's move that session."""
    closes = dict(db.execute(select(IndexDaily.date, IndexDaily.close).where(IndexDaily.symbol == "NIFTY")).all())
    days = sorted(closes)
    move = {d: closes[d] / closes[p] - 1 for p, d in zip(days, days[1:])}
    latest: dict[date, NewsBrief] = {}
    for b in db.scalars(select(NewsBrief).where(NewsBrief.overall.in_(("positive", "negative"))).order_by(NewsBrief.id)):
        latest.setdefault(b.session_date, b)  # the first (morning) brief for each session
    judged = [(b, move[d]) for d, b in latest.items() if d in move]
    agreed = sum(1 for b, m in judged if (m > 0) == (b.overall == "positive"))
    return {"days": len(judged), "agreed": agreed, "min_days": 20}


def pulse(db: Session) -> dict:
    data = cached()
    return {"pulse": data, "scorecard": scorecard(db), "claude": claude_client.enabled(db), "spend": claude_client.spend(db), "checked_at": utcnow().isoformat()}
