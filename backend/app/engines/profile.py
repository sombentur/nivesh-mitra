"""Risk profile, emergency-fund plan and asset split (doc 03, Part A).

Pure functions: answers + rules in, result out. No database, no I/O — easy to test and audit.
"""

import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Category = Literal["conservative", "moderate", "aggressive"]
ORDER: list[str] = ["conservative", "moderate", "aggressive"]


def stricter(a: str, b: str) -> str:
    return a if ORDER.index(a) <= ORDER.index(b) else b


def _label(rules: dict, question: str, value: str) -> str:
    return next(o["label"] for o in rules["questions"][question] if o["value"] == value)


def _band_upto(value: float, bands: list[dict]) -> int:
    for b in bands:
        if b["upto"] is None or value <= b["upto"]:
            return b["points"]
    raise ValueError("bands must end with upto: null")


def _band_atleast(value: float, bands: list[dict]) -> int:
    for b in bands:
        if value >= b["atleast"]:
            return b["points"]
    raise ValueError("bands must end with atleast: 0")


def _months(m: float) -> str:
    return f"{m:g} month" if m == 1 else f"{m:g} months"


def rupees(n: float) -> str:
    """Indian digit grouping: 1250000 → ₹12,50,000."""
    s = str(int(round(n)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"₹{s}"


class ProfileAnswers(BaseModel):
    age: int = Field(ge=18, le=100)
    income_range: str
    monthly_expenses: int = Field(gt=0, le=10_000_000)
    monthly_investable: int = Field(ge=0, le=10_000_000)
    emergency_savings: int = Field(ge=0, le=10_000_000_000)
    monthly_emi: int = Field(ge=0, le=10_000_000)
    horizon: str
    fall_reaction: str
    experience: str

    def check_options(self, rules: dict) -> None:
        q = rules["questions"]
        for field, key in [
            ("income_range", "income_ranges"),
            ("horizon", "horizons"),
            ("fall_reaction", "fall_reactions"),
            ("experience", "experience"),
        ]:
            if getattr(self, field) not in {o["value"] for o in q[key]}:
                raise ValueError(f"Unknown answer for {field}")


class Reason(BaseModel):
    factor: str
    points: int | None = None
    text: str


class EmergencyPlan(BaseModel):
    target: int
    current: int
    months_covered: float
    shortfall: int
    status: Literal["ok", "building", "missing"]
    monthly_to_liquid: int
    months_to_complete: int | None
    first_action: str | None


class Split(BaseModel):
    core: int = Field(ge=0, le=100)
    satellite: int = Field(ge=0, le=100)
    trading: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _sums_to_100(self):
        if self.core + self.satellite + self.trading != 100:
            raise ValueError("The three parts must add up to 100%")
        return self


class ProfileResult(BaseModel):
    rules_version: int
    capacity_score: int
    capacity_category: Category
    tolerance_category: Category
    final_category: Category
    reasons: list[Reason]
    overrides: list[str]
    emergency: EmergencyPlan
    default_split: Split
    sanity_warnings: list[str]


def income_bounds(rules: dict, income_range: str) -> tuple[int, int | None]:
    r = next(o for o in rules["questions"]["income_ranges"] if o["value"] == income_range)
    return r["low"], r["high"]


def emergency_plan(a: ProfileAnswers, rules: dict) -> EmergencyPlan:
    ef = rules["emergency_fund"]
    target = a.monthly_expenses * ef["target_months"]
    months = a.emergency_savings / a.monthly_expenses
    shortfall = max(0, target - a.emergency_savings)

    def share_at(saved: float) -> float:
        covered = saved / a.monthly_expenses
        return next((r["share"] for r in ef["routing"] if covered < r["below_months"]), 0.0)

    monthly_to_liquid = round(a.monthly_investable * share_at(a.emergency_savings))
    months_to_complete: int | None = 0
    if shortfall > 0:
        if a.monthly_investable == 0:
            months_to_complete = None
        else:
            saved, n = float(a.emergency_savings), 0
            while saved < target and n < 600:
                saved += a.monthly_investable * share_at(saved)
                n += 1
            months_to_complete = n

    status = "ok" if shortfall == 0 else ("building" if a.emergency_savings > 0 else "missing")
    first_action = None
    if shortfall > 0:
        first_action = (
            f"Build your emergency fund first: put {rupees(monthly_to_liquid)} a month into a liquid fund "
            f"until you have {rupees(target)} ({ef['target_months']} months of expenses)."
        )
        if months_to_complete:
            first_action += f" At this pace that takes about {months_to_complete} months."
        elif months_to_complete is None:
            first_action += " Add a monthly investing amount to see how long it will take."
    return EmergencyPlan(
        target=target,
        current=a.emergency_savings,
        months_covered=math.floor(months * 10) / 10,  # round down: never overstate the safety net
        shortfall=shortfall,
        status=status,
        monthly_to_liquid=monthly_to_liquid,
        months_to_complete=months_to_complete,
        first_action=first_action,
    )


def assess(a: ProfileAnswers, rules: dict) -> ProfileResult:
    a.check_options(rules)
    cap = rules["capacity"]
    reasons: list[Reason] = []

    age_pts = _band_upto(a.age, cap["age_points"])
    reasons.append(Reason(factor="Age", points=age_pts, text=f"Age {a.age}: more years ahead means more time to recover from market falls."))

    hz_pts = cap["horizon_points"][a.horizon]
    reasons.append(
        Reason(
            factor="Horizon",
            points=hz_pts,
            text=f"You'll need most of this money in: {_label(rules, 'horizons', a.horizon).lower()}. Money needed sooner can't wait out a fall.",
        )
    )

    income_low, income_high = income_bounds(rules, a.income_range)
    emi_ratio = a.monthly_emi / income_low if a.monthly_emi else 0.0
    emi_pts = _band_upto(emi_ratio, cap["emi_ratio_points"])
    reasons.append(
        Reason(
            factor="Loans",
            points=emi_pts,
            text="No EMIs: nothing competing with your investments."
            if not a.monthly_emi
            else f"EMIs take about {emi_ratio:.0%} of your income, so less room to absorb losses.",
        )
    )

    ef = emergency_plan(a, rules)
    ef_pts = _band_atleast(a.emergency_savings / a.monthly_expenses, cap["emergency_months_points"])
    reasons.append(
        Reason(
            factor="Safety net",
            points=ef_pts,
            text=f"Your emergency savings cover {_months(ef.months_covered)} of expenses (target {rules['emergency_fund']['target_months']}).",
        )
    )

    score = age_pts + hz_pts + emi_pts + ef_pts
    mins = cap["category_min_points"]
    capacity: str = "aggressive" if score >= mins["aggressive"] else "moderate" if score >= mins["moderate"] else "conservative"

    tol = rules["tolerance"]
    tolerance: str = tol["fall_reaction"][a.fall_reaction]
    reasons.append(
        Reason(
            factor="Reaction to a fall",
            text=f"If your investments fell 20%, you'd {_label(rules, 'fall_reactions', a.fall_reaction).split(',')[0].lower()}. That points to {tolerance.title()}.",
        )
    )
    cap_by_exp = tol["experience_cap"].get(a.experience)
    if cap_by_exp and ORDER.index(tolerance) > ORDER.index(cap_by_exp):
        tolerance = cap_by_exp
        reasons.append(
            Reason(
                factor="Experience",
                text=f"New investors are capped at {cap_by_exp.title()} for the first 12 months, while you learn how markets behave.",
            )
        )

    final = stricter(capacity, tolerance)
    overrides: list[str] = []
    if a.horizon == "lt1":
        forced = rules["overrides"]["horizon_lt1_forces"]
        if final != forced:
            overrides.append("Money needed within a year shouldn't be in shares, so your profile is set to Conservative.")
        final = forced

    warnings: list[str] = []
    committed = a.monthly_expenses + a.monthly_emi + a.monthly_investable
    if income_high is not None and committed > income_high:
        warnings.append(
            f"Your expenses, EMIs and monthly investing add up to {rupees(committed)}, more than the top of your income range. Please double-check them."
        )
    if a.monthly_investable == 0:
        warnings.append("You entered ₹0 to invest each month. SIP suggestions will need an amount.")

    return ProfileResult(
        rules_version=rules["version"],
        capacity_score=score,
        capacity_category=capacity,
        tolerance_category=tolerance,
        final_category=final,
        reasons=reasons,
        overrides=overrides,
        emergency=ef,
        default_split=Split(**rules["splits"][final]),
        sanity_warnings=warnings,
    )


def split_warnings(split: Split, rules: dict) -> list[str]:
    lim = rules["limits"]
    out = []
    if split.trading > lim["trading_warn_above"]:
        out.append(
            f"Trading is {split.trading}% — above the safe limit of {lim['trading_warn_above']}%. Most individual traders lose money (see the SEBI figures)."
        )
    if split.satellite > lim["satellite_warn_above"]:
        out.append(f"Direct stocks at {split.satellite}% is above the suggested {lim['satellite_warn_above']}% for your core-satellite plan.")
    if split.core < lim["core_warn_below"]:
        out.append(f"Mutual funds (core) at {split.core}% is below the suggested minimum of {lim['core_warn_below']}%.")
    return out


def check_split_allowed(split: Split, rules: dict) -> None:
    if split.trading > rules["limits"]["trading_max"]:
        raise ValueError(f"Trading can't be more than {rules['limits']['trading_max']}% in NiveshMitra.")


def trading_lock_reasons(months_covered: float, paper_complete: bool, rules: dict) -> list[str]:
    reasons = []
    need = rules["emergency_fund"]["trading_unlock_months"]
    if months_covered < need:
        reasons.append(f"Your emergency fund covers {_months(months_covered)}; trading unlocks at {need} months.")
    if not paper_complete:
        reasons.append(f"Finish the {rules['paper_trading_days']}-day paper-trading period first.")
    return reasons


def effective_split(split: Split, trading_locked: bool) -> Split:
    """While trading is locked, its share stays in mutual funds (core)."""
    if not trading_locked or split.trading == 0:
        return split
    return Split(core=split.core + split.trading, satellite=split.satellite, trading=0)


def future_value(amount_today: float, rate: float, years: float) -> int:
    return int(math.ceil(amount_today * (1 + rate) ** max(years, 0)))
