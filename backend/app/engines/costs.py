"""Exact charges for an equity delivery trade on Groww (rules/costs.yaml). Pure functions, rupees in, rupees out."""

from dataclasses import asdict, dataclass


@dataclass
class Charges:
    brokerage: float = 0.0
    stt: float = 0.0
    exchange: float = 0.0
    sebi: float = 0.0
    stamp_duty: float = 0.0
    dp_charge: float = 0.0
    gst: float = 0.0

    @property
    def total(self) -> float:
        return round(sum(asdict(self).values()), 2)

    def as_dict(self) -> dict:
        return {**{k: round(v, 2) for k, v in asdict(self).items()}, "total": self.total}


def brokerage(value: float, r: dict) -> float:
    b = r["brokerage"]
    return min(max(value * b["rate"], b["min"]), b["max"]) if value > 0 else 0.0


def buy_charges(value: float, r: dict) -> Charges:
    c = Charges(
        brokerage=brokerage(value, r),
        stt=value * r["stt_rate"],
        exchange=value * (r["exchange_txn_rate"] + r["ipft_rate"]),
        sebi=value * r["sebi_fee_rate"],
        stamp_duty=value * r["stamp_duty_buy_rate"],
    )
    c.gst = (c.brokerage + c.exchange + c.sebi) * r["gst_rate"]
    return c


def sell_charges(value: float, r: dict) -> Charges:
    c = Charges(
        brokerage=brokerage(value, r),
        stt=value * r["stt_rate"],
        exchange=value * (r["exchange_txn_rate"] + r["ipft_rate"]),
        sebi=value * r["sebi_fee_rate"],
        dp_charge=r["dp_charge_per_sell"] if value >= r["dp_min_debit_value"] else 0.0,
    )
    c.gst = (c.brokerage + c.exchange + c.sebi + c.dp_charge) * r["gst_rate"]
    return c


def intraday_round_trip(buy_value: float, sell_value: float, r: dict) -> float:
    """Total charges (₹) for buying and selling the same day: brokerage both ways, STT on the sell, stamp on the buy, no DP."""
    i = r["intraday"]
    fees = lambda v: v * (r["exchange_txn_rate"] + r["ipft_rate"] + r["sebi_fee_rate"])  # noqa: E731
    b_brok, s_brok = brokerage(buy_value, r), brokerage(sell_value, r)
    gst = (b_brok + s_brok + fees(buy_value) + fees(sell_value)) * r["gst_rate"]
    total = b_brok + s_brok + fees(buy_value) + fees(sell_value) + sell_value * i["stt_sell_rate"] + buy_value * i["stamp_duty_buy_rate"] + gst
    return round(total, 2)


def round_trip(buy_value: float, sell_value: float, r: dict) -> dict:
    b, s = buy_charges(buy_value, r), sell_charges(sell_value, r)
    return {"buy": b.as_dict(), "sell": s.as_dict(), "total": round(b.total + s.total, 2)}


def cost_drag(capital: float, r: dict, risk_share: float, max_position_share: float, price: float = 1000.0,
              stop_pct: float = 0.03, target_r: float = 2.0) -> dict:
    """For a typical trade at this account size: charges in rupees, as a share of the money at risk (R), and the
    win rate needed just to break even with a `target_r` target. Transparent arithmetic, no market data."""
    import math

    risk_per_share = price * stop_pct
    qty = min(math.floor(capital * risk_share / risk_per_share), math.floor(capital * max_position_share / price))
    if qty < 1:
        return {"capital": capital, "qty": 0, "note": f"Can't afford one ₹{price:,.0f} share within the limits"}
    at_risk = qty * risk_per_share
    charges = round_trip(qty * price, qty * price, r)["total"]
    c = charges / at_risk
    breakeven = (1 + c) / (target_r + 1)  # p·(target − c) = (1 − p)·(1 + c)
    return {
        "capital": capital,
        "qty": qty,
        "position": round(qty * price, 2),
        "at_risk": round(at_risk, 2),
        "charges": round(charges, 2),
        "charges_in_r": round(c, 2),
        "breakeven_win_rate": round(min(breakeven, 1.0), 3),
    }


def breakeven_move(buy_value: float, r: dict) -> float:
    """How much the price must rise just to cover the charges of buying and selling (fraction, e.g. 0.02 = 2%)."""
    if buy_value <= 0:
        return 0.0
    return round_trip(buy_value, buy_value, r)["total"] / buy_value
