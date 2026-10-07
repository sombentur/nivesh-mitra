"""Intraday practice: a rule-based plan for the next session and a scoreboard of how the setups did in the last one.

Practice only. None of the same-day setups has passed its test (they lost money after charges), so nothing here is a buy
signal. The plan says whether the rules would trade or stand aside, lists a few stocks worth WATCHING to learn how a
setup behaves, and the scoreboard shows what would have happened — including to the previous plan's watchlist.
"""

from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IndexDaily, Instrument
from app.engines import holidays
from app.engines import intraday as eng
from app.engines.backtest import position_size
from app.engines.costs import intraday_round_trip
from app.services import app_settings, intraday_trading, trading
from app.services.errors import JobSkipped
from app.services.intraday_data import load as load_intraday
from app.services.stock_data import latest_session, load_bars

Progress = Callable[[int, int], None]
WATCHLIST_SIZE = 5
KEEP = 6  # plans and scoreboards kept (about a week)
WATCH_SETUP = "prev_high_breakout"  # the one setup whose levels are known the evening before


def _noop(_d: int, _t: int) -> None:
    pass


def market_filter(db: Session, session_day: date, sma: int) -> dict | None:
    """The setups only trade when the Nifty 50 closed above its `sma`-day average on the session before."""
    rows = db.execute(
        select(IndexDaily.date, IndexDaily.close).where(IndexDaily.symbol == "NIFTY", IndexDaily.date < session_day).order_by(IndexDaily.date.desc()).limit(sma)
    ).all()
    if len(rows) < sma:
        return None
    close, average = rows[0][1], sum(r[1] for r in rows) / sma
    return {"ok": close > average, "nifty": round(close, 2), "average": round(average, 2), "days": sma, "as_of": rows[0][0].isoformat()}


def _setups(db: Session, r: dict) -> list[dict]:
    tested = intraday_trading.latest(db)
    when = {"orb": "from 9:45 AM", "gap_and_go": "from 9:30 AM", "prev_high_breakout": "from 9:30 AM"}
    out = []
    for key, cfg in r["setups"].items():
        row = tested.get(key)
        test = (row.stats_json or {}).get("test") if row else None
        out.append(
            {
                "key": key,
                "label": cfg["label"],
                "plain": cfg["plain"],
                "when": when.get(key, ""),
                "allowed": bool(row and row.allowed),
                "tested": {k: test.get(k) for k in ("trades", "win_rate", "avg_r", "avg_r_before_charges")} if test and test.get("trades") else None,
            }
        )
    return out


def beginner_rules(r: dict, costs: dict, capital: float) -> list[str]:
    risk = capital * r["risk_per_trade"]
    charges = intraday_round_trip(capital, capital, costs)
    return [
        "Practice with pretend money first. Real money stays locked until your practice period ends.",
        f"Trade only on days the Nifty 50 closed above its {r['market_filter_sma']}-day average the day before. Otherwise watch, don't trade.",
        f"At most {r['max_trades_per_day']} trades a day, and risk at most ₹{risk:,.0f} ({r['risk_per_trade']:.0%} of ₹{capital:,.0f}) on each.",
        "No trade in the first 15 minutes (9:15–9:30): prices jump around too much.",
        "Decide the stop-loss before you buy, and place it as an order straight after buying.",
        f"Sell everything by {_clock(r['exit_time'])}, whatever the price. Never carry an intraday trade overnight.",
        "No borrowed money: buy only what your own cash covers.",
        f"Stop for the day after {r['max_trades_per_day']} losing trades. Don't try to win it back.",
        f"Charges: buying and selling ₹{capital:,.0f} of shares the same day costs about ₹{charges:,.0f}, so a trade must rise more than {charges / capital:.2%} just to break even.",
    ]


def _clock(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    return f"{h - 12 if h > 12 else h}:{m:02d} {'PM' if h >= 12 else 'AM'}"


def _watchlist(db: Session, as_of: date, r: dict, costs: dict, capital: float) -> list[dict]:
    """Stocks that meet the "yesterday's-high breakout" pre-conditions after the `as_of` session, with the levels the
    rules would use the next day. The most-traded ones first."""
    s = r["setups"][WATCH_SETUP]
    slip = costs["intraday"]["slippage_rate"]
    found = []
    for inst in db.scalars(select(Instrument).where(Instrument.in_universe.is_(True))):
        bars = load_bars(db, inst.id, since=as_of - timedelta(days=60))
        if len(bars) < s["trend_sma"] + 1 or bars.index[-1].date() != as_of:
            continue
        last = bars.iloc[-1]
        span = last.high - last.low
        trend_ok = last.close > bars["close"].rolling(s["trend_sma"]).mean().iloc[-1]
        if not trend_ok or span <= 0 or (last.close - last.low) / span < s["prev_close_in_top"] or last.close < r["min_price"]:
            continue
        high, close = float(last.high), float(last.close)  # plain numbers: the plan is stored as JSON
        entry = round(high * (1 + s["trigger_buffer"]) * (1 + slip), 2)
        stop = round(entry * (1 - s["stop_pct"]), 2)
        qty = position_size(entry, stop, capital, r["risk_per_trade"], r["max_position_share"])
        if qty < 1:
            continue  # one share already risks more than the practice account allows
        target = round(entry + s["target_r"] * (entry - stop), 2)
        charges = float(intraday_round_trip(entry * qty, target * qty, costs))
        found.append(
            {
                "symbol": inst.symbol,
                "name": inst.name or inst.symbol,
                "prev_close": round(close, 2),
                "prev_high": round(high, 2),
                "trigger": round(high * (1 + s["trigger_buffer"]), 2),
                "entry": entry,
                "stop": stop,
                "target": target,
                "qty": qty,
                "amount": round(entry * qty, 2),
                "risk": round((entry - stop) * qty, 2),
                "reward": round((target - entry) * qty - charges, 2),
                "charges": charges,
                "traded_cr": round(float((bars["close"] * bars["volume"]).tail(20).mean()) / 1e7, 1),
            }
        )
    found.sort(key=lambda x: -x["traded_cr"])
    return found[:WATCHLIST_SIZE]


def build_plan(db: Session, session_day: date) -> dict | None:
    """The practice plan for `session_day`, from prices up to the trading day before it. None until those prices are in."""
    as_of = latest_session(db)
    if as_of is None or as_of != holidays.prev_trading_day(session_day):
        return None
    r, costs, capital = intraday_trading.rules(), trading.cost_rules(), trading.capital(db)
    flt = market_filter(db, session_day, r["market_filter_sma"])
    if flt is None:
        return None
    return {
        "session": session_day.isoformat(),
        "based_on": as_of.isoformat(),
        "capital": capital,
        "filter": flt,
        "verdict": "practice" if flt["ok"] else "stand_aside",
        "setups": _setups(db, r),
        "watch_setup": r["setups"][WATCH_SETUP]["label"],
        "watchlist": _watchlist(db, as_of, r, costs, capital),
        "rules": beginner_rules(r, costs, capital),
        "max_trades": r["max_trades_per_day"],
        "exit_time": _clock(r["exit_time"]),
    }


def _trade_view(t: eng.IntradayTrade) -> dict:
    return {
        "symbol": t.symbol,
        "setup": t.setup,
        "entry_time": t.entry_time,
        "entry": float(t.entry),
        "exit_time": t.exit_time,
        "exit": float(t.exit),
        "exit_reason": t.exit_reason,
        "qty": int(t.qty),
        "net_pnl": float(t.net_pnl),
        "r": float(t.r_multiple),
    }


def build_recap(db: Session, day: date, plan: dict | None = None) -> dict | None:
    """How each setup would have done on `day` for the practice account, whatever the market filter said — and what
    happened to that day's watchlist. None if the day's 15-minute bars aren't in yet."""
    r, costs, capital = intraday_trading.rules(), trading.cost_rules(), trading.capital(db)
    setups = [k for k, v in r["setups"].items() if v.get("enabled", True)]
    trades: dict[str, list[eng.IntradayTrade]] = {k: [] for k in setups}
    stamp, since = pd.Timestamp(day), pd.Timestamp(day - timedelta(days=75))
    seen = 0
    for inst in db.scalars(select(Instrument).where(Instrument.in_universe.is_(True))):
        bars = load_intraday(inst.symbol)
        bars = bars[bars.index >= since]
        today = bars[bars.index.normalize() == stamp]
        if today.empty:
            continue
        seen += 1
        daily = load_bars(db, inst.id, since=day - timedelta(days=120))
        ctx = intraday_trading._contexts(daily, bars[bars.index < stamp + timedelta(days=1)], {day: True}, r["setups"]["orb"]["trend_sma"]).get(day)
        if ctx is None:
            continue
        day_bars = next(b for d, b in intraday_trading._sessions(today) if d == day)
        for k in setups:
            t = eng.simulate(inst.symbol, k, ctx, day_bars, r, costs, capital)
            if t:
                trades[k].append(t)
    if not seen:
        return None
    flt = market_filter(db, day, r["market_filter_sma"])
    everything = sorted((t for ts in trades.values() for t in ts), key=lambda t: (t.entry_time, t.symbol))
    watch = []
    for w in (plan or {}).get("watchlist", []):
        hit = next((t for t in trades.get(WATCH_SETUP, []) if t.symbol == w["symbol"]), None)
        watch.append({"symbol": w["symbol"], "trigger": w["trigger"], "outcome": _trade_view(hit) if hit else None})
    return {
        "date": day.isoformat(),
        "capital": capital,
        "stocks": seen,
        "filter_ok": bool(flt and flt["ok"]),
        "setups": [
            {
                "key": k,
                "label": r["setups"][k]["label"],
                "signals": len(ts),
                "won": sum(1 for t in ts if t.net_pnl > 0),
                "target": sum(1 for t in ts if t.exit_reason == "target"),
                "stopped": sum(1 for t in ts if t.exit_reason == "stop"),
                "avg_r": round(float(sum(t.r_multiple for t in ts)) / len(ts), 2) if ts else None,
                "avg_pnl": round(float(sum(t.net_pnl for t in ts)) / len(ts), 2) if ts else None,
            }
            for k, ts in trades.items()
        ],
        # the rules allow only the first few signals of a day: what those would have made or lost
        "first_trades": [_trade_view(t) for t in everything[: r["max_trades_per_day"]]],
        "watchlist": watch,
    }


def plan_missing(db: Session) -> bool:
    """Prices are in, but the practice plan for the next session hasn't been written yet."""
    latest = latest_session(db)
    if latest is None:
        return False
    return holidays.next_trading_day(latest).isoformat() not in stored(db)[0]


def stored(db: Session) -> tuple[dict, dict]:
    return app_settings.get_setting(db, "intraday_plans") or {}, app_settings.get_setting(db, "intraday_recaps") or {}


def _keep(d: dict) -> dict:
    return {k: d[k] for k in sorted(d)[-KEEP:]}


def after_close(db: Session, progress: Progress = _noop) -> str:
    """After prices are in: score the session just finished and write the practice plan for the next one."""
    latest = latest_session(db)
    if latest is None:
        raise JobSkipped("Waiting for stock prices")
    plans, recaps = stored(db)
    recap = build_recap(db, latest, plans.get(latest.isoformat()))
    if recap:
        recaps[latest.isoformat()] = recap
    nxt = holidays.next_trading_day(latest)
    plan = build_plan(db, nxt)
    if plan:
        plans[nxt.isoformat()] = plan
    app_settings.set_setting(db, "intraday_plans", _keep(plans))
    app_settings.set_setting(db, "intraday_recaps", _keep(recaps))
    db.commit()
    if not plan:
        return f"Scoreboard for {latest:%d %b} {'made' if recap else 'not ready'}; no plan yet"
    verdict = "practice trades allowed" if plan["verdict"] == "practice" else "stand aside (Nifty below its average)"
    return f"Plan for {nxt:%a %d %b}: {verdict}; {len(plan['watchlist'])} stocks to watch. Scoreboard for {latest:%d %b} {'made' if recap else 'not ready'}"
