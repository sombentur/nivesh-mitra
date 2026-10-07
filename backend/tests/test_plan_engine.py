import pytest

from app.engines import plan as p
from app.rules import load_rules

R = load_rules("plan")


def test_long_goal_keeps_template():
    assert p.horizon_allocation(R["templates"]["moderate"], R, 10) == R["templates"]["moderate"]


def test_medium_goal_caps_equity_at_50():
    a = p.horizon_allocation(R["templates"]["aggressive"], R, 4)
    equity = sum(v * R["slots"][s]["equity_share"] for s, v in a.items())
    assert sum(a.values()) == 100 and 49 <= equity <= 51
    assert a["short_duration"] > R["templates"]["aggressive"]["short_duration"]


def test_near_goal_caps_equity_at_20_and_counts_hybrid_as_half():
    a = p.horizon_allocation(R["templates"]["conservative"], R, 2)
    equity = sum(v * R["slots"][s]["equity_share"] for s, v in a.items())
    assert sum(a.values()) == 100 and 19 <= equity <= 21


def test_goal_within_a_year_is_liquid_only():
    assert p.horizon_allocation(R["templates"]["aggressive"], R, 0) == {"liquid": 100}


def test_sip_maths():
    # ₹10,000 a month for 10 years at 12% a year (start-of-month) ≈ ₹22.4 lakh
    assert p.fv_sip(10000, 0.12, 120) == pytest.approx(2_24_0000, rel=0.01)
    need = p.required_sip(2_24_0000, 0, 0.12, 120)
    assert need == pytest.approx(10000, rel=0.01)
    assert p.required_sip(100, 1000, 0.1, 12) == 0  # corpus already enough
    assert p.required_sip(1200, 0, 0.0, 12) == pytest.approx(100)


def test_blended_rates_follow_the_mix():
    cons, exp, opt = p.blended_rates({"liquid": 100}, R)
    assert (cons, exp, opt) == tuple(R["scenario_returns"]["liquid"])
    c2 = p.blended_rates({"nifty_50_index": 50, "short_duration": 50}, R)[0]
    assert c2 == pytest.approx((0.07 + 0.055) / 2)


def test_split_sip_rounds_and_merges_small_slices():
    alloc = {"nifty_50_index": 35, "flexi_cap": 15, "balanced_advantage": 20, "short_duration": 30}
    s = p.split_sip(2000, alloc, R)  # flexi slice ₹300 < ₹500 → folded into the biggest equity slot
    assert sum(s.values()) == 2000 and "flexi_cap" not in s and all(v % 100 == 0 for v in s.values())
    big = p.split_sip(20000, alloc, R)
    assert big == {"nifty_50_index": 7000, "flexi_cap": 3000, "balanced_advantage": 4000, "short_duration": 6000}
    assert p.split_sip(0, alloc, R) == {}


def test_cost_of_regular_plan():
    # ₹5,000/month for 10 years at 12%, Regular costing 0.6% a year more
    lost = p.cost_of_regular(5000, 0.12, 0.006)
    assert 30000 < lost < 45000
