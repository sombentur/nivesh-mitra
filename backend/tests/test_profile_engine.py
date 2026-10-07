import pytest
from pydantic import ValidationError

from app.engines import profile as eng
from app.rules import load_rules

RULES = load_rules("profile")


def answers(**kw) -> eng.ProfileAnswers:
    base = dict(
        age=28,
        income_range="50kto1l",  # cautious end: ₹50,000
        monthly_expenses=30000,
        monthly_investable=20000,
        emergency_savings=200000,  # 6.6 months
        monthly_emi=0,
        horizon="5plus",
        fall_reaction="buy_more",
        experience="stocks_2plus",
    )
    base.update(kw)
    return eng.ProfileAnswers(**base)


def test_max_capacity_and_tolerance_is_aggressive():
    r = eng.assess(answers(), RULES)
    assert r.capacity_score == 16
    assert (r.capacity_category, r.tolerance_category, r.final_category) == ("aggressive", "aggressive", "aggressive")
    assert r.default_split == eng.Split(core=65, satellite=25, trading=10)
    assert r.emergency.status == "ok" and r.emergency.first_action is None


def test_new_investor_is_capped_at_moderate():
    r = eng.assess(answers(experience="none"), RULES)
    assert r.capacity_category == "aggressive"
    assert r.tolerance_category == "moderate"
    assert r.final_category == "moderate"
    assert any(x.factor == "Experience" for x in r.reasons)


def test_profile_is_the_stricter_of_capacity_and_tolerance():
    r = eng.assess(answers(fall_reaction="sell"), RULES)
    assert r.capacity_category == "aggressive" and r.final_category == "conservative"


def test_short_horizon_forces_conservative():
    r = eng.assess(answers(horizon="lt1"), RULES)
    assert r.final_category == "conservative"
    assert r.overrides


@pytest.mark.parametrize("age,points", [(18, 4), (29, 4), (30, 3), (39, 3), (40, 2), (49, 2), (50, 1), (80, 1)])
def test_age_bands(age, points):
    r = eng.assess(answers(age=age), RULES)
    assert next(x for x in r.reasons if x.factor == "Age").points == points


@pytest.mark.parametrize("emi,points", [(0, 4), (5000, 3), (10000, 3), (10001, 2), (20000, 2), (20001, 1)])
def test_emi_ratio_bands_use_cautious_income(emi, points):
    r = eng.assess(answers(monthly_emi=emi), RULES)  # ratio = emi / 50,000
    assert next(x for x in r.reasons if x.factor == "Loans").points == points


@pytest.mark.parametrize(
    "score_parts,category",
    [
        (dict(age=28, horizon="5plus", monthly_emi=0, emergency_savings=90000), "aggressive"),  # 4+4+4+3 = 15
        (dict(age=45, horizon="3to5", monthly_emi=15000, emergency_savings=90000), "moderate"),  # 2+3+2+3 = 10
        (dict(age=45, horizon="1to3", monthly_emi=15000, emergency_savings=30000), "conservative"),  # 2+2+2+2 = 8
        (dict(age=35, horizon="3to5", monthly_emi=0, emergency_savings=90000), "aggressive"),  # 3+3+4+3 = 13
        (dict(age=35, horizon="3to5", monthly_emi=0, emergency_savings=30000), "moderate"),  # 3+3+4+2 = 12
        (dict(age=45, horizon="1to3", monthly_emi=15000, emergency_savings=90000), "moderate"),  # 2+2+2+3 = 9
    ],
)
def test_capacity_category_boundaries(score_parts, category):
    assert eng.assess(answers(**score_parts), RULES).capacity_category == category


def test_emergency_plan_routes_everything_then_half():
    # target 6 × 50,000 = 3,00,000. 100% of 20,000 until 3 months (8 months), then 50% → 14 more months.
    r = eng.assess(answers(monthly_expenses=50000, emergency_savings=0, income_range="1lto2l"), RULES)
    e = r.emergency
    assert (e.target, e.shortfall, e.status) == (300000, 300000, "missing")
    assert e.monthly_to_liquid == 20000
    assert e.months_to_complete == 22
    assert "₹20,000" in e.first_action and "₹3,00,000" in e.first_action
    assert next(x for x in r.reasons if x.factor == "Safety net").points == 1


def test_emergency_months_never_overstated():
    e = eng.emergency_plan(answers(monthly_expenses=50000, emergency_savings=299999), RULES)
    assert e.months_covered == 5.9 and e.status == "building"
    assert e.monthly_to_liquid == 10000  # already past 3 months → half


def test_emergency_plan_without_investable_amount():
    e = eng.emergency_plan(answers(monthly_investable=0, emergency_savings=0), RULES)
    assert e.months_to_complete is None and "Add a monthly investing amount" in e.first_action


def test_sanity_warning_when_numbers_exceed_income():
    r = eng.assess(answers(income_range="lt30k", monthly_expenses=25000, monthly_investable=10000), RULES)
    assert r.sanity_warnings


def test_split_rules():
    with pytest.raises(ValidationError):
        eng.Split(core=70, satellite=20, trading=5)
    eng.check_split_allowed(eng.Split(core=60, satellite=20, trading=20), RULES)
    with pytest.raises(ValueError):
        eng.check_split_allowed(eng.Split(core=59, satellite=20, trading=21), RULES)
    assert eng.split_warnings(eng.Split(core=75, satellite=20, trading=5), RULES) == []
    w = eng.split_warnings(eng.Split(core=45, satellite=36, trading=19), RULES)
    assert len(w) == 3


def test_locked_trading_share_stays_in_core():
    s = eng.effective_split(eng.Split(core=65, satellite=25, trading=10), trading_locked=True)
    assert s == eng.Split(core=75, satellite=25, trading=0)
    assert len(eng.trading_lock_reasons(2.9, paper_complete=False, rules=RULES)) == 2
    assert eng.trading_lock_reasons(3.0, paper_complete=True, rules=RULES) == []


@pytest.mark.parametrize("n,text", [(999, "₹999"), (100000, "₹1,00,000"), (1250000, "₹12,50,000"), (12345678, "₹1,23,45,678")])
def test_indian_rupee_format(n, text):
    assert eng.rupees(n) == text


def test_unknown_option_rejected():
    with pytest.raises(ValueError):
        eng.assess(answers(horizon="forever"), RULES)
