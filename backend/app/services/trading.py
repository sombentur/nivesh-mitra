"""Short-term (swing) trading: backtests, daily ideas, and the practice (paper) account.

Real money is never involved here: every idea is marked `is_paper` while your practice period runs or trading is
locked (doc 04, R-15), and NiveshMitra never places orders anywhere.
"""

from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.http import SourceUnavailable
from app.db.base import utcnow
from app.db.models import Instrument, PaperAccount, PaperTrade, Recommendation, SetupBacktest
from app.engines import backtest as bt
from app.engines import holidays
from app.engines.costs import breakeven_move, round_trip
from app.engines.setups import find_signals, prepare
from app.rules import load_rules
from app.services import app_settings, strategy_versions
from app.services.errors import JobSkipped
from app.services.stock_data import latest_session, load_bars

Progress = Callable[[int, int], None]
MAX_IDEAS_PER_DAY = 5
STALE_AFTER_DAYS = 4  # R-13: no ideas from prices older than this


class TradingBlocked(ValueError):
    """A risk rule refuses the action; the message says which and why."""


def _noop(_d: int, _t: int) -> None:
    pass


def rules() -> dict:
    return load_rules("trading")


def cost_rules() -> dict:
    return load_rules("costs")


def capital(db: Session) -> float:
    return float(app_settings.get_setting(db, "trading_paper_capital") or rules()["paper"]["start_capital"])


def next_session(d: date) -> date:
    """The next trading day after `d`: weekends and listed exchange holidays are skipped (rules/market_holidays.yaml).
    A holiday missing from that list is still handled when prices arrive: a pending order waits for the next real session."""
    return holidays.next_trading_day(d)


def account(db: Session) -> PaperAccount:
    acct = db.scalar(select(PaperAccount).where(PaperAccount.kind == "trading", PaperAccount.closed_at.is_(None)))
    if acct is None:
        acct = PaperAccount(kind="trading", start_capital=capital(db))
        db.add(acct)
        db.flush()
    return acct


def _version(db: Session):
    r, c = rules(), cost_rules()
    return strategy_versions.get_or_create(db, "swing", {"version": r["version"], "trading": r, "costs": c})


# ------------------------------------------------------------------------------------------------ backtests
def run_backtests(db: Session, progress: Progress = _noop) -> str:
    r, c, cap = rules(), cost_rules(), capital(db)
    insts = db.scalars(select(Instrument).where(Instrument.in_universe.is_(True), Instrument.history_start.is_not(None))).all()
    if not insts:
        raise JobSkipped("Waiting for stock price history — backtests start by themselves once it's downloaded")
    by_setup: dict[str, list[bt.Trade]] = {k: [] for k, v in r["setups"].items() if v.get("enabled", True)}
    for n, inst in enumerate(insts):
        bars = load_bars(db, inst.id)
        if len(bars) >= 260:
            ind = prepare(bars, r)
            for sig in find_signals(ind, r):
                t = bt.simulate(inst.symbol, bars, sig, cap, r["risk"], c)
                if t:
                    by_setup[sig.setup].append(t)
        progress(n + 1, len(insts))
    version = _version(db)
    lines = []
    for setup, trades in by_setup.items():
        stats = bt.summarise(trades, cap, r["backtest"]["max_positions"])
        ok, why = bt.verdict(stats, r)
        db.add(SetupBacktest(setup=setup, strategy_version_id=version.id, capital=cap, universe_size=len(insts), stats_json=stats, allowed=ok, verdict=why))
        lines.append(f"{r['setups'][setup]['label']}: {'ON' if ok else 'OFF'} ({why})")
    db.commit()
    return "; ".join(lines)


def latest_backtests(db: Session) -> dict[str, SetupBacktest]:
    """Newest result per swing setup (same-day setups share the table under "intraday:…" and are kept out)."""
    out: dict[str, SetupBacktest] = {}
    for row in db.scalars(select(SetupBacktest).where(SetupBacktest.setup.not_like("intraday:%")).order_by(SetupBacktest.id.desc())):
        out.setdefault(row.setup, row)
    return out


# ------------------------------------------------------------------------------------------------ risk state
def state(db: Session) -> dict:
    """Cooling-off (R-10), daily loss limit (R-06) and open positions for the practice account."""
    r, cap = rules(), capital(db)
    acct = account(db)
    last = latest_session(db)
    trades = db.scalars(select(PaperTrade).where(PaperTrade.account_id == acct.id).order_by(PaperTrade.exit_date, PaperTrade.id)).all()
    closed = [t for t in trades if t.status == "closed"]
    open_n = sum(1 for t in trades if t.status in ("pending", "open"))
    blocked_until, reason = None, None

    co, long_co = r["risk"]["cooling_off"], r["risk"]["cooling_off_long"]
    recent = closed[-co["losses_in_a_row"] :]
    if len(recent) == co["losses_in_a_row"] and all((t.net_pnl or 0) <= 0 for t in recent):
        until = _add_sessions(recent[-1].exit_date, co["days"])
        if last is None or until > last:
            blocked_until, reason = until, f"{co['losses_in_a_row']} losing trades in a row — take {co['days']} trading days off (R-10)"
    window = closed[-long_co["out_of_last"] :]
    if sum(1 for t in window if (t.net_pnl or 0) <= 0) >= long_co["losses"]:
        until = _add_sessions(window[-1].exit_date, long_co["days"])
        if (last is None or until > last) and (blocked_until is None or until > blocked_until):
            blocked_until, reason = until, f"{long_co['losses']} losses in your last {long_co['out_of_last']} trades — take {long_co['days']} trading days off (R-10)"

    day_loss = -sum(t.net_pnl or 0 for t in closed if last and t.exit_date == last)
    loss_hit = day_loss >= r["risk"]["daily_loss_limit"] * cap
    realized = sum(t.net_pnl or 0 for t in closed)
    return {
        "capital": cap,
        "account_start_capital": acct.start_capital,
        "realized_pnl": round(realized, 2),
        "open_positions": open_n,
        "max_open_positions": r["paper"]["max_open_positions"],
        "cooling_off_until": blocked_until.isoformat() if blocked_until else None,
        "cooling_off_reason": reason,
        "loss_limit_hit": loss_hit,
        "loss_limit_reason": f"Lost ₹{day_loss:,.0f} on {last:%d %b} — over the {r['risk']['daily_loss_limit']:.0%} daily limit (R-06). No new ideas until the next session." if loss_hit else None,
        "latest_session": last.isoformat() if last else None,
    }


def _add_sessions(d: date, n: int) -> date:
    for _ in range(n):
        d = next_session(d)
    return d


def _blocked_reason(st: dict) -> str | None:
    return st["cooling_off_reason"] or st["loss_limit_reason"]


# ------------------------------------------------------------------------------------------------ daily ideas
def _confidence(stats: dict) -> str:
    if stats.get("trades", 0) >= 300 and stats.get("avg_r", 0) >= 0.2:
        return "high"
    if stats.get("avg_r", 0) >= 0.1:
        return "medium"
    return "low"


def generate_ideas(db: Session, progress: Progress = _noop) -> str:
    r, c, cap = rules(), cost_rules(), capital(db)
    as_of = latest_session(db)
    if as_of is None:
        raise SourceUnavailable("No stock prices yet — ideas need Groww market data")
    if as_of < utcnow().date() - timedelta(days=STALE_AFTER_DAYS):
        _record(db, as_of, None, 0, f"Prices are from {as_of:%d %b} — too old to act on (R-13). Data unavailable.")
        raise SourceUnavailable(f"Stock prices are stale (last session {as_of}) — no ideas today")
    session = next_session(as_of)
    if db.scalar(select(Recommendation.id).where(Recommendation.engine == "swing", Recommendation.data_as_of == as_of)):
        return f"Ideas for {session:%d %b} already made"
    for old in db.scalars(select(Recommendation).where(Recommendation.engine == "swing", Recommendation.status == "open", Recommendation.for_session < session)):
        old.status = "expired"

    st = state(db)
    if (why := _blocked_reason(st)) is not None:
        _record(db, as_of, session, 0, why)
        db.commit()
        return why
    bts = latest_backtests(db)
    allowed = {k for k, v in bts.items() if v.allowed}
    if not allowed:
        why = "No setup has passed its backtest yet, so there are no ideas. That's the rule: only strategies that made money after costs in the past."
        _record(db, as_of, session, 0, why)
        db.commit()
        return why

    candidates = []
    insts = db.scalars(select(Instrument).where(Instrument.in_universe.is_(True))).all()
    for n, inst in enumerate(insts):
        bars = load_bars(db, inst.id, since=as_of - timedelta(days=450))
        if len(bars) >= 210 and bars.index[-1].date() == as_of:
            for sig in find_signals(prepare(bars, r), r, only_last_day=True):
                if sig.setup in allowed:
                    qty = bt.position_size(sig.entry_high, sig.stop, cap, r["risk"]["risk_per_trade"], r["risk"]["max_position_share"])
                    if qty >= 1:
                        candidates.append((inst, sig, qty))
        progress(n + 1, len(insts))
    candidates.sort(key=lambda x: (-bts[x[1].setup].stats_json.get("avg_r", 0), (x[1].entry_high - x[1].stop) / x[1].entry_high))
    version = _version(db)
    for inst, sig, qty in candidates[:MAX_IDEAS_PER_DAY]:
        db.add(_idea(inst, sig, qty, session, as_of, bts[sig.setup].stats_json, r, c, version.id))
    made = min(len(candidates), MAX_IDEAS_PER_DAY)
    _record(db, as_of, session, made, None if made else "No stock matched a tested setup today. No trade today is a valid answer.")
    db.commit()
    return f"{made} idea(s) for {session:%d %b}" if made else f"No trade for {session:%d %b}"


def _record(db: Session, as_of: date, session: date | None, count: int, reason: str | None) -> None:
    app_settings.set_setting(
        db,
        "trading_ideas_status",
        {"as_of": as_of.isoformat(), "for_session": session.isoformat() if session else None, "count": count, "reason": reason, "at": utcnow().isoformat()},
    )


def _idea(inst: Instrument, sig, qty: int, session: date, as_of: date, stats: dict, r: dict, c: dict, version_id: int) -> Recommendation:
    buy_value = sig.entry_high * qty
    charges = round_trip(buy_value, sig.target * qty, c)["total"]
    risk_amt = (sig.entry_high - sig.stop) * qty
    setup = r["setups"][sig.setup]
    win = stats.get("win_rate") or 0
    streak = f" (worst run in testing: {stats['max_losing_streak']})" if stats.get("max_losing_streak") else ""
    return Recommendation(
        engine="swing",
        setup=sig.setup,
        instrument_id=inst.id,
        action="buy",
        confidence=_confidence(stats),
        entry_low=sig.entry_low,
        entry_high=sig.entry_high,
        stop_loss=sig.stop,
        target=sig.target,
        horizon_days=sig.max_hold_days,
        qty=qty,
        amount=round(buy_value, 2),
        rationale_json={
            "symbol": inst.symbol,
            "name": inst.name,
            "setup_label": setup["label"],
            "setup_plain": setup["plain"],
            "reasons": sig.reasons,
            "reward_risk": round(sig.reward_risk_worst, 2),
            "risk_amount": round(risk_amt, 2),
            "reward_amount": round((sig.target - sig.entry_high) * qty, 2),
            "charges": charges,
            "breakeven_pct": round(breakeven_move(buy_value, c), 4),
            "backtest": {k: stats.get(k) for k in ("trades", "win_rate", "avg_r", "profit_factor", "avg_hold_days", "max_losing_streak", "period")},
            "close": sig.close,
        },
        risks_json=[
            f"In past tests this setup lost money on {1 - win:.0%} of trades. Expect losses, sometimes several in a row{streak}.",
            f"Charges of about ₹{charges:,.0f} mean the price must rise {breakeven_move(buy_value, c):.1%} just to break even.",
            "Bad news can make a stock open below your stop-loss; the loss would then be bigger than planned.",
            "This idea comes from price patterns only. It doesn't yet check company news or results dates (that arrives with the stock engine).",
        ],
        groww_steps_json=[
            f"Open Groww, search for {inst.symbol} ({inst.name}) and tap Buy.",
            "Choose Delivery (not Intraday).",
            f"Order type Limit, price ₹{sig.entry_high:,.2f}, quantity {qty}. Don't chase it higher.",
            f"Once it's bought, set a stop-loss (GTT) sell for {qty} shares at ₹{sig.stop:,.2f}, and a target sell at ₹{sig.target:,.2f}.",
            f"If it isn't bought on {session:%d %b}, cancel the order. The idea expires.",
        ],
        strategy_version_id=version_id,
        data_as_of=as_of,
        for_session=session,
        is_paper=True,
        status="open",
    )


def open_ideas(db: Session) -> list[Recommendation]:
    last = latest_session(db)
    stmt = select(Recommendation).where(Recommendation.engine == "swing", Recommendation.status.in_(("open", "taken")))
    if last:
        stmt = stmt.where(Recommendation.for_session > last)
    return db.scalars(stmt.order_by(Recommendation.id)).all()


# ------------------------------------------------------------------------------------------------ paper trading
def place_paper_trade(db: Session, rec_id: int, qty: int) -> PaperTrade:
    rec = db.get(Recommendation, rec_id)
    last = latest_session(db)
    if rec is None or rec.engine != "swing":
        raise TradingBlocked("Idea not found")
    if rec.status != "open" or (last and rec.for_session <= last):
        raise TradingBlocked("This idea has expired or was already taken")
    st = state(db)
    if (why := _blocked_reason(st)) is not None:
        raise TradingBlocked(why)
    if st["open_positions"] >= st["max_open_positions"]:
        raise TradingBlocked(f"You already have {st['open_positions']} practice trades open — the limit is {st['max_open_positions']}")
    if not 1 <= qty <= (rec.qty or 0):
        raise TradingBlocked(f"Quantity must be between 1 and {rec.qty} — more would risk over 1% of your capital (R-05)")
    t = PaperTrade(
        account_id=account(db).id, recommendation_id=rec.id, instrument_id=rec.instrument_id, setup=rec.setup, status="pending", qty=qty,
        entry_low=rec.entry_low, entry_high=rec.entry_high, stop=rec.stop_loss, target=rec.target, max_hold_days=rec.horizon_days,
        for_session=rec.for_session,
    )
    rec.status = "taken"
    db.add(t)
    db.commit()
    return t


def cancel_paper_trade(db: Session, trade_id: int) -> PaperTrade:
    t = db.get(PaperTrade, trade_id)
    if t is None or t.status != "pending":
        raise TradingBlocked("Only a trade that hasn't been bought yet can be cancelled")
    t.status = "cancelled"
    db.commit()
    return t


def close_paper_trade(db: Session, trade_id: int) -> PaperTrade:
    """Sell now at the last closing price (a manual exit)."""
    t = db.get(PaperTrade, trade_id)
    if t is None or t.status != "open":
        raise TradingBlocked("Only an open trade can be closed")
    bars = load_bars(db, t.instrument_id, since=t.entry_date)
    last = bars.iloc[-1]
    _close(t, round(float(last.close) * (1 - cost_rules()["slippage_rate"]), 2), "manual", bars.index[-1].date(), len(bars))
    db.commit()
    return t


def _close(t: PaperTrade, price: float, reason: str, day: date, days_held: int) -> None:
    rt = round_trip(t.entry_price * t.qty, price * t.qty, cost_rules())
    t.exit_price, t.exit_reason, t.exit_date, t.days_held = round(price, 2), reason, day, days_held
    t.charges_json = rt
    t.net_pnl = round((price - t.entry_price) * t.qty - rt["total"], 2)
    t.r_multiple = round(t.net_pnl / ((t.entry_price - t.stop) * t.qty), 3)
    t.status = "closed"


def process_paper(db: Session, progress: Progress = _noop) -> str:
    """After prices arrive: fill pending practice orders at the open, then check stops, targets and time limits."""
    slip = cost_rules()["slippage_rate"]
    filled = missed = closed = 0
    for t in db.scalars(select(PaperTrade).where(PaperTrade.status.in_(("pending", "open")))).all():
        bars = load_bars(db, t.instrument_id, since=t.entry_date or t.for_session)
        if bars.empty:
            continue
        if t.status == "pending":
            first = bars.iloc[0]
            price = bt.entry_fill(first, t.entry_high, t.stop, slip)
            if price is None:
                t.status, t.exit_reason = "missed", "opened outside the entry range"
                missed += 1
                continue
            t.status, t.entry_price, t.entry_date = "open", price, bars.index[0].date()
            filled += 1
        window = bars[bars.index >= str(t.entry_date)].iloc[: t.max_hold_days]
        for i, (day, bar) in enumerate(window.iterrows()):
            hit = bt.exit_fill(bar, i == 0, t.stop, t.target, slip)
            if hit:
                _close(t, hit[0], hit[1], day.date(), i + 1)
                break
        else:
            t.days_held = len(window)
            if len(window) >= t.max_hold_days:
                _close(t, float(window.iloc[-1].close) * (1 - slip), "time", window.index[-1].date(), len(window))
        closed += t.status == "closed"
    db.commit()
    return f"Practice trades: {filled} bought, {missed} missed, {closed} closed"


def after_close(db: Session, progress: Progress = _noop) -> str:
    return f"{process_paper(db)}; {generate_ideas(db, progress)}"


def paper_summary(db: Session) -> dict:
    acct = account(db)
    trades = db.scalars(select(PaperTrade).where(PaperTrade.account_id == acct.id).order_by(PaperTrade.id.desc())).all()
    closed = [t for t in trades if t.status == "closed"]
    unrealized = 0.0
    for t in trades:
        if t.status == "open":
            bars = load_bars(db, t.instrument_id, since=t.entry_date)
            if not bars.empty:
                unrealized += (float(bars.iloc[-1].close) - t.entry_price) * t.qty
    wins = [t for t in closed if (t.net_pnl or 0) > 0]
    realized = sum(t.net_pnl or 0 for t in closed)
    return {
        "start_capital": acct.start_capital,
        "started": acct.created_at.isoformat(),
        "equity": round(acct.start_capital + realized + unrealized, 2),
        "realized_pnl": round(realized, 2),
        "unrealized_pnl": round(unrealized, 2),
        "charges_paid": round(sum((t.charges_json or {}).get("total", 0) for t in closed), 2),
        "closed_trades": len(closed),
        "win_rate": round(len(wins) / len(closed), 3) if closed else None,
        "avg_r": round(sum(t.r_multiple or 0 for t in closed) / len(closed), 3) if closed else None,
        "trades": trades,
    }


def reset_account(db: Session) -> PaperAccount:
    acct = account(db)
    if any(t.status in ("pending", "open") for t in db.scalars(select(PaperTrade).where(PaperTrade.account_id == acct.id))):
        raise TradingBlocked("Close or cancel your open practice trades first")
    acct.closed_at = utcnow()
    db.flush()
    new = account(db)
    db.commit()
    return new
