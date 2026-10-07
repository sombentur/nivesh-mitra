"""The decision-first dashboard: market mood, next session's stock ideas, and the best fund for each time horizon."""

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IndexDaily, User
from app.engines.indicators import sma
from app.services import day_strip, mf_scores, trading
from app.services import plan as plan_svc
from app.services import profile as profile_svc

CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def _index(db: Session, symbol: str, days: int) -> pd.Series:
    since = date.today() - timedelta(days=days)
    rows = db.execute(select(IndexDaily.date, IndexDaily.close).where(IndexDaily.symbol == symbol, IndexDaily.date >= since).order_by(IndexDaily.date)).all()
    return pd.Series([r[1] for r in rows], index=pd.DatetimeIndex([r[0] for r in rows]), dtype=float)


def market(db: Session) -> dict | None:
    """Nifty 50 trend (vs its 50- and 200-day averages) and India VIX → a plain mood label. Not a forecast."""
    nifty = _index(db, "NIFTY", 420)
    if len(nifty) < 210:
        return None
    rules = trading.rules().get("market_mood", {"vix_calm": 15, "vix_nervous": 20})
    last, prev = float(nifty.iloc[-1]), float(nifty.iloc[-2])
    d50, d200 = float(sma(nifty, 50).iloc[-1]), float(sma(nifty, 200).iloc[-1])
    vix_s = _index(db, "INDIAVIX", 30)
    vix = float(vix_s.iloc[-1]) if len(vix_s) else None
    nervous = vix is not None and vix > rules["vix_nervous"]
    if last > d50 > d200 and not nervous:
        mood, tone = "Positive", "good"
    elif (last < d50 < d200) or (last < d200 and nervous):
        mood, tone = "Weak", "bad"
    else:
        mood, tone = "Mixed", "warn"
    parts = [
        f"Nifty 50 at {last:,.0f} is {'above' if last > d50 else 'below'} its 50-day average ({d50:,.0f})",
        f"{'above' if last > d200 else 'below'} its 200-day average ({d200:,.0f})",
    ]
    if vix is not None:
        calm = "calm" if vix < rules["vix_calm"] else ("nervous" if nervous else "normal")
        parts.append(f"India VIX {vix:.1f} ({calm})")
    chart = nifty[nifty.index >= nifty.index[-1] - pd.DateOffset(months=6)]
    return {
        "mood": mood,
        "tone": tone,
        "reason": "; ".join(parts) + ".",
        "nifty": round(last, 2),
        "change_pct": round(last / prev - 1, 4),
        "as_of": nifty.index[-1].date().isoformat(),
        "vix": round(vix, 2) if vix is not None else None,
        "chart": [[d.date().isoformat(), round(float(v), 2)] for d, v in chart.items()],
    }


def _best(db: Session, category: str) -> dict | None:
    index_group = "Nifty 50" if category == "Index Fund – Equity" else None
    rows = mf_scores.top_in(db, category=None if index_group else category, index_group_label=index_group, limit=10)
    if not rows:
        return None
    s, f = sorted(rows, key=lambda x: (CONFIDENCE_ORDER.get(x[1].confidence, 3) > 1, -(x[1].total or 0)))[0]
    m = f.metrics_json or {}
    return {
        "scheme_code": s.scheme_code,
        "name": s.display_name,
        "category": "Nifty 50 index fund" if index_group else category,
        "score": f.total,
        "rank": f.rank,
        "peers": f.peers,
        "confidence": f.confidence,
        "ter": m.get("ter"),
        "fee": mf_scores.latest_fee(db, s.scheme_code),
        "typical_1y": m.get("rr1_med"),
        "typical_3y": m.get("rr3_med"),
        "typical_5y": m.get("rr5_med"),
        "worst_fall": m.get("maxdd_5y"),
        "worst_month": m.get("worst_1m"),
        "reason": (f.reasons_for_json or [None])[0],
    }


def horizon_picks(db: Session, user: User) -> list[dict]:
    prof = profile_svc.current_profile(db, user)
    category = prof.final_category if prof else "moderate"
    out = []
    for h in plan_svc.rules()["horizon_picks"]:
        cats = h.get("categories") or h["categories_by_profile"][category]
        picks = [p for p in (_best(db, c) for c in cats) if p]
        out.append({"key": h["key"], "label": h["label"], "why": h["why"], "picks": picks})
    return out


def build(db: Session, user: User) -> dict:
    """Stock ideas and the practice account come from /api/trading (same views as the Trading page)."""
    return {"market": market(db), "horizons": horizon_picks(db, user), "days": day_strip.build(db)}
