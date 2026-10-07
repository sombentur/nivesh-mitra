"""Your mutual fund plan: emergency fund first, then a SIP per goal, using the best-scored Direct funds (doc 03 §C5–C9)."""


import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import FundScore, Goal, MfScheme, User
from app.engines import mf_metrics as mm
from app.engines import plan as eng
from app.rules import load_rules
from app.services import mf_data, mf_scores
from app.services import profile as profile_svc

CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


class PlanUnavailable(ValueError):
    pass


def rules() -> dict:
    return load_rules("plan")


def _returns(db: Session, code: int) -> pd.Series:
    s = mm.to_series(mf_data.nav_series(db, code))
    return s[s.index > s.index[-1] - pd.DateOffset(years=3)].pct_change().dropna() if not s.empty else s


class FundPicker:
    """One fund per slot for the whole plan (fewer SIPs to manage), chosen from the latest scores."""

    def __init__(self, db: Session, r: dict):
        self.db, self.r = db, r
        self.picked: dict[str, tuple[MfScheme, FundScore]] = {}
        self._active_returns: list[pd.Series] = []

    def pick(self, slot: str) -> tuple[MfScheme, FundScore] | None:
        if slot in self.picked:
            return self.picked[slot]
        cfg = self.r["slots"][slot]
        rows = mf_scores.top_in(self.db, category=cfg.get("category"), index_group_label=cfg.get("index_group"), limit=15)
        if not rows:
            return None
        min_rank = CONFIDENCE_ORDER[self.r["min_confidence"]]
        ordered = sorted(rows, key=lambda x: (CONFIDENCE_ORDER.get(x[1].confidence, 3) > min_rank, -(x[1].total or 0)))
        choice = ordered[0]
        if cfg.get("active_equity"):
            for cand in ordered:
                rets = _returns(self.db, cand[0].scheme_code)
                if all(_corr(rets, other) <= self.r["max_similarity"] for other in self._active_returns):
                    choice = cand
                    self._active_returns.append(rets)
                    break
        self.picked[slot] = choice
        return choice


def _corr(a: pd.Series, b: pd.Series) -> float:
    both = pd.concat([a, b], axis=1).dropna()
    return float(both.corr().iloc[0, 1]) if len(both) > 60 else 0.0


def _fund_view(s: MfScheme, f: FundScore) -> dict:
    m = f.metrics_json or {}
    return {
        "scheme_code": s.scheme_code,
        "name": s.display_name,
        "category": s.category,
        "score": f.total,
        "rank": f.rank,
        "peers": f.peers,
        "confidence": f.confidence,
        "ter": m.get("ter"),
        "regular_cost_gap": m.get("regular_cost_gap"),
        "rr5_med": m.get("rr5_med"),
        "rr3_med": m.get("rr3_med"),
        "maxdd_5y": m.get("maxdd_5y"),
        "reasons_for": f.reasons_for_json or [],
        "reasons_against": f.reasons_against_json or [],
    }


def _groww_steps(name: str, monthly: int, lumpsum: bool = False) -> list[str]:
    return [
        f"Open Groww → Mutual Funds and search for “{name.split(' - ')[0]}”.",
        "Check the fund page says Direct and Growth (Groww shows Direct plans by default).",
        f"Tap SIP, enter ₹{monthly:,} a month and choose a date a few days after your salary arrives."
        if not lumpsum
        else f"Tap One-time and invest ₹{monthly:,}.",
        "Approve the UPI AutoPay / bank mandate when Groww asks. That's it — it runs every month by itself.",
    ]


def build_plan(db: Session, user: User) -> dict:
    prof = profile_svc.current_profile(db, user)
    if prof is None:
        raise PlanUnavailable("Finish your risk profile first.")
    run = mf_scores.latest_run(db)
    if run is None:
        raise PlanUnavailable("Fund scores aren't ready yet — they're calculated after the fund history download.")
    r = rules()
    view = profile_svc.profile_view(db, prof)
    result, answers = prof.result_json, prof.answers_json
    picker = FundPicker(db, r)
    today = utcnow().date()

    # ---- budget
    investable = int(answers.get("monthly_investable") or 0)
    ef = result["emergency"]
    to_liquid = int(ef["monthly_to_liquid"])
    after_ef = max(0, investable - to_liquid)
    eff = view["allocation"]["effective"]
    mf_budget = int(after_ef * eff["core"] / 100 // r["round_to"] * r["round_to"])
    stocks_budget = after_ef - mf_budget

    # ---- emergency fund
    emergency = None
    if ef["shortfall"] > 0:
        pick = picker.pick("liquid")
        emergency = {
            "target": ef["target"],
            "current": ef["current"],
            "shortfall": ef["shortfall"],
            "monthly": to_liquid,
            "months_to_complete": ef["months_to_complete"],
            "fund": _fund_view(*pick) if pick else None,
            "groww_steps": _groww_steps(pick[0].display_name, to_liquid) if pick and to_liquid else [],
        }

    # ---- goals
    goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id, Goal.archived_at.is_(None)).order_by(Goal.priority, Goal.target_year)
    ).all()
    template = r["templates"][result["final_category"]]
    remaining = mf_budget
    goal_views = []
    for g in goals:
        months = eng.months_until(g.target_year, today)
        years = months // 12
        target = g.target_amount_today * (1 + g.inflation_rate) ** (months / 12)
        alloc = eng.horizon_allocation(template, r, years)
        rates = eng.blended_rates(alloc, r)
        need = [eng.required_sip(target, g.current_corpus, rate, months) for rate in rates]
        recommended = eng.round_up(need[0], r["round_to"])
        affordable = min(recommended, remaining)
        remaining -= affordable
        split = eng.split_sip(recommended, alloc, r)
        funds = []
        for slot, amount in split.items():
            pick = picker.pick(slot)
            fv = _fund_view(*pick) if pick else None
            gap = (fv or {}).get("regular_cost_gap")
            funds.append(
                {
                    "slot": slot,
                    "label": r["slots"][slot]["label"],
                    "share": alloc.get(slot, 0),
                    "monthly": amount,
                    "fund": fv,
                    "regular_would_cost_10y": round(eng.cost_of_regular(amount, rates[1], gap)) if gap else None,
                }
            )
        goal_views.append(
            {
                "id": g.id,
                "name": g.name,
                "target_year": g.target_year,
                "months_away": months,
                "years_away": round(months / 12, 1),
                "target_today": g.target_amount_today,
                "target_future": round(target),
                "current_corpus": g.current_corpus,
                "allocation": alloc,
                "equity_share": round(sum(p * r["slots"][s]["equity_share"] for s, p in alloc.items())),
                "rates": [round(x, 4) for x in rates],
                "sip_needed": {"conservative": round(need[0]), "expected": round(need[1]), "optimistic": round(need[2])},
                "recommended_sip": recommended,
                "affordable_now": affordable,
                "funds": funds,
                "projection_if_recommended": [round(g.current_corpus * (1 + x) ** (months / 12) + eng.fv_sip(recommended, x, months)) for x in rates],
            }
        )

    # ---- your SIPs, one per fund (what you'd actually set up on Groww)
    sips: dict[int, dict] = {}
    for gv in goal_views:
        scale = gv["affordable_now"] / gv["recommended_sip"] if gv["recommended_sip"] else 0
        for f in gv["funds"]:
            if not f["fund"]:
                continue
            code = f["fund"]["scheme_code"]
            row = sips.setdefault(code, {"fund": f["fund"], "label": f["label"], "monthly_needed": 0, "monthly_affordable": 0, "goals": []})
            row["monthly_needed"] += f["monthly"]
            row["monthly_affordable"] += f["monthly"] * scale
            row["goals"].append(gv["name"])
    for row in sips.values():
        row["monthly_affordable"] = int(row["monthly_affordable"] // r["round_to"] * r["round_to"])
        row["groww_steps"] = _groww_steps(row["fund"]["name"], row["monthly_affordable"] or row["monthly_needed"])

    total_needed = sum(g["recommended_sip"] for g in goal_views)
    notes = []
    if emergency and to_liquid >= investable:
        notes.append(
            f"For now, all of your ₹{investable:,} a month goes to the emergency fund. Goal SIPs start once it covers "
            f"{load_rules('profile')['emergency_fund']['routing'][0]['below_months']} months of expenses."
        )
    if total_needed > mf_budget:
        notes.append(
            f"Your goals need about ₹{total_needed:,} a month (planned conservatively), but ₹{mf_budget:,} is available for mutual "
            "funds right now. Options: invest more later (SIPs can step up each year), move a goal's year, or lower a target. "
            "Goals are funded in order of priority, then date."
        )
    if stocks_budget > 0:
        notes.append(f"₹{stocks_budget:,} a month is set aside for your direct-stocks/trading share of the split (see My profile).")

    return {
        "generated_at": utcnow().isoformat(),
        "scores_as_of": run.data_as_of.isoformat(),
        "profile": result["final_category"],
        "budget": {"investable": investable, "to_emergency_fund": to_liquid, "for_mutual_funds": mf_budget, "for_stocks": stocks_budget, "goals_need": total_needed},
        "emergency": emergency,
        "goals": goal_views,
        "sips": sorted(sips.values(), key=lambda x: -x["monthly_needed"]),
        "notes": notes,
        "assumptions": {k: v for k, v in r["scenario_returns"].items()},
    }
