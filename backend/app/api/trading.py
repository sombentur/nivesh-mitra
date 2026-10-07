"""Short-term trading: today's ideas, the practice (paper) account, backtests, and the Groww connection check.

Practice only — NiveshMitra never places orders. The "What to do on Groww" steps are for you to follow yourself.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.connectors.http import SourceUnavailable
from app.db.base import get_db
from app.db.models import DataSourceStatus, Instrument, PaperTrade, Recommendation, User
from app.engines import costs as costs_engine
from app.engines.profile import trading_lock_reasons
from app.services import app_settings, groww_service, trendlyne_service
from app.services import intraday_trading
from app.services import profile as profile_svc
from app.services import trading as svc
from app.services.audit import audit
from app.services.stock_data import SOURCE_PRICES, latest_session

router = APIRouter(prefix="/api/trading", tags=["trading"])


class PaperBuy(BaseModel):
    qty: int


def _idea_view(rec: Recommendation) -> dict:
    return {
        "id": rec.id,
        "setup": rec.setup,
        "status": rec.status,
        "for_session": rec.for_session.isoformat() if rec.for_session else None,
        "data_as_of": rec.data_as_of.isoformat() if rec.data_as_of else None,
        "confidence": rec.confidence,
        "entry_low": rec.entry_low,
        "entry_high": rec.entry_high,
        "stop": rec.stop_loss,
        "target": rec.target,
        "hold_days": rec.horizon_days,
        "qty": rec.qty,
        "amount": rec.amount,
        "is_paper": rec.is_paper,
        **(rec.rationale_json or {}),
        "risks": rec.risks_json or [],
        "groww_steps": rec.groww_steps_json or [],
    }


def _trade_view(t: PaperTrade, symbols: dict[int, tuple[str, str]]) -> dict:
    sym, name = symbols.get(t.instrument_id, ("?", "?"))
    return {
        "id": t.id,
        "symbol": sym,
        "name": name,
        "setup": t.setup,
        "status": t.status,
        "qty": t.qty,
        "entry_low": t.entry_low,
        "entry_high": t.entry_high,
        "stop": t.stop,
        "target": t.target,
        "for_session": t.for_session.isoformat(),
        "entry_date": t.entry_date.isoformat() if t.entry_date else None,
        "entry_price": t.entry_price,
        "exit_date": t.exit_date.isoformat() if t.exit_date else None,
        "exit_price": t.exit_price,
        "exit_reason": t.exit_reason,
        "days_held": t.days_held,
        "charges": (t.charges_json or {}).get("total"),
        "net_pnl": t.net_pnl,
        "r_multiple": t.r_multiple,
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(current_user)):
    st = svc.state(db)
    prof = profile_svc.current_profile(db, user)
    paper = profile_svc.paper_status(db)
    months = prof.result_json["emergency"]["months_covered"] if prof else 0
    real_locked = trading_lock_reasons(months, paper["complete"], profile_svc.rules())
    if prof is not None:
        split = profile_svc.profile_view(db, prof)["allocation"]["target"]
        if split["trading"] == 0:
            real_locked.append("Your split gives trading 0% (change it on My profile — raising it waits 24 hours).")
    price_status = db.get(DataSourceStatus, SOURCE_PRICES)
    universe = db.scalar(select(func.count()).where(Instrument.in_universe.is_(True))) or 0
    last = latest_session(db)
    db.commit()  # account() may have created the practice account
    return {
        "state": st,
        "ideas_status": app_settings.get_setting(db, "trading_ideas_status"),
        "practice": paper,
        "real_money_locked": real_locked,
        "data": {
            "latest_session": last.isoformat() if last else None,
            "universe_size": universe,
            "prices_ok": bool(price_status and price_status.healthy),
            "prices_error": price_status.last_error if price_status else None,
        },
    }


@router.get("/ideas")
def ideas(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [_idea_view(r) for r in svc.open_ideas(db)]


@router.post("/ideas/{rec_id}/paper-buy")
def paper_buy(rec_id: int, body: PaperBuy, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        t = svc.place_paper_trade(db, rec_id, body.qty)
    except svc.TradingBlocked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    audit(db, user.email, "paper_trade_placed", recommendation_id=rec_id, qty=body.qty)
    db.commit()
    return {"ok": True, "trade_id": t.id}


def _symbols(db: Session) -> dict[int, tuple[str, str]]:
    return {i: (s, n) for i, s, n in db.execute(select(Instrument.id, Instrument.symbol, Instrument.name))}


@router.get("/paper")
def paper(db: Session = Depends(get_db), user: User = Depends(current_user)):
    summary = svc.paper_summary(db)
    db.commit()
    syms = _symbols(db)
    summary["trades"] = [_trade_view(t, syms) for t in summary["trades"]]
    return summary


@router.post("/paper/{trade_id}/cancel")
def cancel(trade_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        svc.cancel_paper_trade(db, trade_id)
    except svc.TradingBlocked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return {"ok": True}


@router.post("/paper/{trade_id}/close")
def close(trade_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        svc.close_paper_trade(db, trade_id)
    except svc.TradingBlocked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return {"ok": True}


@router.post("/paper/reset")
def reset(db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        acct = svc.reset_account(db)
    except svc.TradingBlocked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    audit(db, user.email, "paper_account_reset", capital=acct.start_capital)
    db.commit()
    return {"ok": True, "start_capital": acct.start_capital}


@router.get("/backtests")
def backtests(db: Session = Depends(get_db), user: User = Depends(current_user)):
    r = svc.rules()
    latest = svc.latest_backtests(db)
    out = []
    for key, cfg in r["setups"].items():
        b = latest.get(key)
        out.append(
            {
                "setup": key,
                "label": cfg["label"],
                "plain": cfg["plain"],
                "enabled": cfg.get("enabled", True),
                "tested": b is not None,
                "allowed": bool(b and b.allowed),
                "verdict": b.verdict if b else "Not tested yet — waits for price history",
                "run_at": b.run_at.isoformat() if b else None,
                "capital": b.capital if b else None,
                "universe_size": b.universe_size if b else None,
                "stats": {k: v for k, v in (b.stats_json if b else {}).items() if k != "portfolio"} if b else None,
                "portfolio": (b.stats_json or {}).get("portfolio") if b else None,
            }
        )
    return out


@router.get("/intraday")
def intraday(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """The same-day setups and how they did: built on 2020–23, judged on 2024 onwards."""
    r = intraday_trading.rules()
    latest = intraday_trading.latest(db)
    out = []
    for key, cfg in r["setups"].items():
        b = latest.get(key)
        stats = b.stats_json if b else {}
        out.append(
            {
                "setup": key,
                "label": cfg["label"],
                "plain": cfg["plain"],
                "enabled": cfg.get("enabled", True),
                "tested": b is not None,
                "allowed": bool(b and b.allowed),
                "verdict": b.verdict if b else "Not tested yet — waits for 15-minute price history",
                "run_at": b.run_at.isoformat() if b else None,
                "capital": b.capital if b else None,
                "build": stats.get("build"),
                "test": stats.get("test"),
                "test_avg_r_at_1_lakh": stats.get("test_avg_r_at_1_lakh"),
                "recent": stats.get("recent", []),
            }
        )
    return out


@router.get("/cost-drag")
def cost_drag(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """What Groww's charges do to a typical ₹1,000 stock trade (3% stop, 2R target) at different account sizes."""
    r, c = svc.rules(), svc.cost_rules()
    sizes = sorted({svc.capital(db), 10000, 25000, 50000, 100000, 200000})
    return {
        "assumptions": "A ₹1,000 share, stop-loss 3% below the buy price, target 2× the risk, 1% of capital at risk, at most 35% of capital in one trade.",
        "your_capital": svc.capital(db),
        "rows": [costs_engine.cost_drag(s, c, r["risk"]["risk_per_trade"], r["risk"]["max_position_share"]) for s in sizes],
    }


@router.post("/trendlyne-check")
def trendlyne_check(sample: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """List Trendlyne's tools (free); with sample=true also look up one stock (uses 1 call of your plan)."""
    result = trendlyne_service.diagnose(db, sample=sample)
    audit(db, user.email, "trendlyne_connection_checked", ok=result["ok"], sample=sample)
    db.commit()
    return result


@router.post("/groww-check")
def groww_check(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Log in to Groww and test each kind of read-only access. Makes a handful of API calls."""
    try:
        result = groww_service.diagnose(db)
    except SourceUnavailable as exc:
        return {"auth_method": None, "login": {"ok": False, "detail": str(exc)}, "portfolio": None, "prices": None, "history": None}
    audit(db, user.email, "groww_connection_checked", prices_ok=bool(result.get("prices") and result["prices"]["ok"]))
    db.commit()
    return result
