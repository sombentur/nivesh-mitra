"""Sector pages: the companies behind each sector tile on the dashboard (rules/sectors.yaml).

Information, not advice. The sector tile shows NSE's sector index; the page below it lists the tracked companies whose
main business is that sector, grouped by industry, with the same numbers as the stock snapshots.
"""

from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IndexDaily
from app.rules import load_rules
from app.services import market

HISTORY_DAYS = 400  # about a year of daily index closes for the chart


class UnknownSector(KeyError):
    pass


@lru_cache
def rules() -> dict:
    """rules/sectors.yaml, checked once: every industry named anywhere must be defined."""
    r = load_rules("sectors")
    industries = r["industries"]
    for key, s in r["sectors"].items():
        missing = [i for i in s["industries"] if i not in industries]
        if missing:
            raise ValueError(f"sector {key} names unknown industries {missing}")
    bad = {sym: ind for sym, ind in r["companies"].items() if ind not in industries}
    if bad:
        raise ValueError(f"companies with unknown industries: {bad}")
    return r


def industry_of(symbol: str) -> str | None:
    return rules()["companies"].get(symbol)


def tile_keys() -> dict[str, str]:
    """NSE sector index symbol -> sector page key, for the dashboard tiles and index cards."""
    return {s["index"]: key for key, s in rules()["sectors"].items() if s.get("index")}


def _members(stocks: dict[str, dict], industries: list[str]) -> list[dict]:
    """Industry groups in the given order, each with its tracked companies, biggest riser first."""
    labels = rules()["industries"]
    groups = []
    for ind in industries:
        companies = sorted((s for s in stocks.values() if industry_of(s["symbol"]) == ind), key=lambda s: -s["change_pct"])
        if companies:
            groups.append({"industry": ind, "label": labels[ind], "companies": companies})
    return groups


def _summary(companies: list[dict]) -> dict:
    n = len(companies)
    up = sum(1 for c in companies if c["change_pct"] > 0.0005)
    down = sum(1 for c in companies if c["change_pct"] < -0.0005)
    avg = round(sum(c["change_pct"] for c in companies) / n, 4) if n else None
    best = max(companies, key=lambda c: c["change_pct"], default=None)
    worst = min(companies, key=lambda c: c["change_pct"], default=None)
    return {
        "companies": n,
        "advancers": up,
        "decliners": down,
        "unchanged": n - up - down,
        "avg_change_pct": avg,
        "best": {"symbol": best["symbol"], "change_pct": best["change_pct"]} if best else None,
        "worst": {"symbol": worst["symbol"], "change_pct": worst["change_pct"]} if worst else None,
    }


def _index_card(snap: dict, sym: str | None, name: str | None) -> dict | None:
    i = snap["_all_indices"].get(sym) if sym else None
    if not i:
        return None
    return {k: i[k] for k in ("symbol", "last", "change", "change_pct", "spark", "ret_1w", "ret_1m", "ret_3m", "ret_1y", "high_52w", "low_52w", "from_high", "trend", "as_of")} | {"name": name or sym}


def _common(snap: dict) -> dict:
    return {
        "as_of": snap["as_of"],
        "live": snap["live"],
        "market_open": snap["market_open"],
        "updated_at": snap["updated_at"],
        "checked": str(rules()["checked"]),
        "tracked": len(snap["stocks"]),
    }


def overview(db: Session) -> dict:
    """Every sector with its index move (if it has one) and how its tracked companies did."""
    snap = market.snapshot(db)
    stocks = snap["stocks"]
    sectors = []
    for key, s in rules()["sectors"].items():
        companies = [c for g in _members(stocks, s["industries"]) for c in g["companies"]]
        sectors.append(
            {
                "key": key,
                "label": s["label"],
                "about": s["about"],
                "index": _index_card(snap, s.get("index"), s.get("index_name")),
                "summary": _summary(companies),
            }
        )
    unclassified = sorted(sym for sym in stocks if industry_of(sym) is None)
    return _common(snap) | {"sectors": sectors, "unclassified": unclassified}


def detail(db: Session, key: str) -> dict:
    """One sector: its index (with about a year of closes for the chart) and its companies grouped by industry."""
    s = rules()["sectors"].get(key)
    if s is None:
        raise UnknownSector(key)
    snap = market.snapshot(db)
    groups = _members(snap["stocks"], s["industries"])
    companies = [c for g in groups for c in g["companies"]]
    history: list[list] = []
    if s.get("index"):
        since = datetime.now(market.IST).date() - timedelta(days=HISTORY_DAYS)
        rows = db.execute(
            select(IndexDaily.date, IndexDaily.close).where(IndexDaily.symbol == s["index"], IndexDaily.date >= since).order_by(IndexDaily.date)
        ).all()
        history = [[d.isoformat(), float(c)] for d, c in rows]
    return _common(snap) | {
        "key": key,
        "label": s["label"],
        "about": s["about"],
        "industries": [{"key": i, "label": rules()["industries"][i]} for i in s["industries"]],
        "index": _index_card(snap, s.get("index"), s.get("index_name")),
        "history": history,
        "summary": _summary(companies),
        "groups": groups,
        "others": [{"key": k, "label": o["label"]} for k, o in rules()["sectors"].items() if k != key],
    }

