"""SIP and portfolio maths (doc 03 §C6, §C7, §C9). Pure functions."""

import math
from datetime import date

GOAL_MONTH = 7  # goals only have a year, so we plan for the middle of it (July) — cautious for goals early in the year


def months_until(target_year: int, today: date) -> int:
    """Months from today to the middle of the goal's year (at least 1)."""
    return max(1, (target_year - today.year) * 12 + (GOAL_MONTH - today.month))


def horizon_allocation(template: dict[str, float], rules: dict, years: int) -> dict[str, int]:
    """Template split, made safer for closer goals: equity capped by years-to-goal; the excess goes to the debt slot."""
    slots = rules["slots"]
    cap_rule = next(c for c in rules["horizon_caps"] if years >= c["min_years"])
    if cap_rule.get("liquid_only"):
        return {"liquid": 100}
    equity = sum(p * slots[s]["equity_share"] for s, p in template.items())
    out = dict(template)
    if equity > cap_rule["equity_cap"]:
        k = cap_rule["equity_cap"] / equity
        freed = 0.0
        for s, p in template.items():
            if slots[s]["equity_share"] > 0:
                out[s] = p * k
                freed += p - out[s]
        out[rules["debt_slot"]] = out.get(rules["debt_slot"], 0) + freed
    return _round_to_100(out)


def _round_to_100(parts: dict[str, float]) -> dict[str, int]:
    floors = {k: math.floor(v) for k, v in parts.items()}
    short = 100 - sum(floors.values())
    for k in sorted(parts, key=lambda k: parts[k] - floors[k], reverse=True)[:short]:
        floors[k] += 1
    return {k: v for k, v in floors.items() if v > 0}


def blended_rates(alloc: dict[str, int], rules: dict) -> tuple[float, float, float]:
    """Conservative / expected / optimistic yearly return for this mix."""
    sr, slots = rules["scenario_returns"], rules["slots"]
    return tuple(sum(p / 100 * sr[slots[s]["scenario"]][i] for s, p in alloc.items()) for i in range(3))  # type: ignore[return-value]


def monthly_rate(r: float) -> float:
    return (1 + r) ** (1 / 12) - 1


def sip_factor(r: float, months: int) -> float:
    """Future value of ₹1 a month for `months` months, paid at the start of each month."""
    i = monthly_rate(r)
    return months if i == 0 else ((1 + i) ** months - 1) / i * (1 + i)


def fv_sip(monthly: float, r: float, months: int) -> float:
    return monthly * sip_factor(r, months)


def required_sip(target: float, corpus: float, r: float, months: int) -> float:
    grown = corpus * (1 + r) ** (months / 12)
    return max(0.0, (target - grown) / sip_factor(r, months))


def round_up(x: float, step: int) -> int:
    return int(math.ceil(x / step) * step) if x > 0 else 0


def split_sip(total: int, alloc: dict[str, int], rules: dict) -> dict[str, int]:
    """Rupees per slot. Slices under the minimum SIP are folded into the biggest slot of the same kind (equity/debt)."""
    if total <= 0:
        return {}
    slots, step, minimum = rules["slots"], rules["round_to"], rules["min_sip_per_fund"]
    raw = {s: total * p / 100 for s, p in alloc.items()}
    kind = lambda s: "equity" if slots[s]["equity_share"] > 0 else "debt"  # noqa: E731
    for s in sorted(raw, key=raw.get):
        if raw[s] < minimum and len(raw) > 1:
            same = [o for o in raw if o != s and kind(o) == kind(s)] or [o for o in raw if o != s]
            biggest = max(same, key=raw.get)
            raw[biggest] += raw.pop(s)
    rounded = {s: int(round(v / step) * step) for s, v in raw.items()}
    rounded[max(raw, key=raw.get)] += total - sum(rounded.values())  # the biggest slice absorbs rounding
    return {s: v for s, v in rounded.items() if v > 0}


def cost_of_regular(monthly: float, r: float, gap: float, years: int = 10) -> float:
    """₹ lost over `years` by choosing the Regular plan (return lower by `gap` a year) instead of Direct."""
    n = years * 12
    return fv_sip(monthly, r, n) - fv_sip(monthly, max(r - gap, 0.0), n)
