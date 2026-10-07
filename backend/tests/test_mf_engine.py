import io
import zipfile
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.connectors import amfi_ter
from app.db.base import SessionLocal, utcnow
from app.db.models import FundScore, Goal, MfScheme, MfSchemeFacts, NavDaily, User
from app.engines import mf_metrics as mm
from app.engines import mf_scoring as sc
from app.engines.profile import ProfileAnswers
from app.rules import load_rules
from app.services import mf_scores, plan
from app.services import profile as profile_svc
from tests.conftest import CSRF

R = load_rules("mf_scoring")


# ------------------------------------------------------------------ scoring engine
def test_percentiles_with_ties_and_direction():
    p = sc.percentiles({1: 10, 2: 20, 3: 20, 4: 30}, higher_is_better=True)
    assert p == {1: 0.0, 2: 50.0, 3: 50.0, 4: 100.0}
    assert sc.percentiles({1: 0.5, 2: 1.5}, higher_is_better=False) == {1: 100.0, 2: 0.0}
    assert sc.percentiles({1: None, 2: 3.0}, True) == {2: 50.0}


def _fund(i, **kw):
    base = dict(history_years=6, rr3_med=0.10 + i / 100, rr5_med=0.11 + i / 100, rr7_med=0.12, beat_bench_3y=0.5, beat_cat_3y=0.5,
                maxdd_5y=-0.3, downcap_3y=0.9, rr3_p10=0.05, sortino_3y=1.0, sharpe_3y=0.8, ter=0.01)
    base.update(kw)
    return base


def test_score_group_ranks_and_explains():
    funds = {i: _fund(i) for i in range(1, 7)}
    funds[6]["ter"] = 0.004
    out = sc.score_group(funds, "equity", R, {"category": "Flexi Cap Fund", "bench_label": "Nifty 500"})
    best = max(out.values(), key=lambda s: s.total)
    assert best.scheme_code == 6 and best.rank == 1 and best.peers == 6
    assert any("Flexi Cap funds" in r for r in best.reasons_for)  # "Fund funds" tidied
    assert best.coverage == pytest.approx(0.9)  # manager tenure + AUM not available yet
    assert best.confidence == "medium"  # only 6 peers (high needs 15)


def test_not_applicable_metrics_do_not_lower_coverage():
    funds = {i: _fund(i, beat_bench_3y=None, downcap_3y=None) for i in range(1, 7)}
    na = sc.score_group(funds, "equity", R, {"category": "Balanced Advantage"}, not_applicable=frozenset({"beat_bench_3y", "downcap_3y"}))
    missing = sc.score_group(funds, "equity", R, {"category": "Balanced Advantage"})
    assert na[1].coverage > missing[1].coverage


def test_young_funds_and_small_categories_are_unranked():
    funds = {i: _fund(i) for i in range(1, 7)}
    funds[1]["history_years"] = 2
    out = sc.score_group(funds, "equity", R, {"category": "X"})
    assert out[1].confidence == "unranked" and "3 years" in out[1].unranked_reason
    small = sc.score_group({i: _fund(i) for i in range(1, 4)}, "equity", R, {"category": "X"})
    assert all(s.total is None and "too few" in s.unranked_reason for s in small.values())


def test_index_group_matching():
    g = lambda n: (sc.index_group(n, R) or {}).get("key")  # noqa: E731
    assert g("UTI Nifty 50 Index Fund - Direct Plan - Growth Option") == "nifty_50"
    assert g("ICICI Prudential NIFTY50 Index Fund Direct Growth") == "nifty_50"
    assert g("DSP Nifty 50 Equal Weight Index Fund - Direct - Growth") is None
    assert g("Motilal Oswal Nifty Midcap 150 Index Fund - Direct") == "nifty_midcap_150"
    assert g("HDFC Nifty Next 50 Index Fund - Direct") == "nifty_next_50"


# ------------------------------------------------------------------ metrics
def _series(years=8, growth=0.12, seed=0, vol=0.0):
    idx = pd.bdate_range(end="2026-09-29", periods=int(252 * years))
    rng = np.random.default_rng(seed)
    daily = (1 + growth) ** (1 / 252) - 1 + rng.normal(0, vol, len(idx))
    return pd.Series(100 * np.cumprod(1 + daily), index=idx)


def test_rolling_cagr_matches_constant_growth():
    s = _series(growth=0.12)
    ends = mm.grid(s.index[-1], 10)
    r3 = mm.rolling_cagr(s, 3, ends).dropna()
    assert len(r3) > 100 and r3.median() == pytest.approx(0.12, abs=0.01)
    assert mm.max_drawdown(s, 5, s.index[-1]) == pytest.approx(0.0, abs=1e-9)


def test_drawdown_and_share_above():
    s = _series()
    s.iloc[-300:-200] *= 0.7
    assert mm.max_drawdown(s, 5, s.index[-1]) == pytest.approx(-0.3, abs=0.01)
    a = pd.Series([1, 2, 3] * 5, dtype=float)
    assert mm.share_above(a, pd.Series([2.0] * 15)) == pytest.approx(1 / 3)


# ------------------------------------------------------------------ AMFI TER file (both layouts)
def _xlsx(headers: list[str], rows: list[list]) -> bytes:
    def cell(col, r, v):
        if isinstance(v, str):
            return f'<c r="{col}{r}" t="inlineStr"><is><t>{v}</t></is></c>'
        return f'<c r="{col}{r}"><v>{v}</v></c>'

    cols = [chr(65 + i) for i in range(len(headers))]
    xml_rows = ["<row>" + "".join(cell(c, 1, h) for c, h in zip(cols, headers)) + "</row>"]
    for n, row in enumerate(rows, start=2):
        xml_rows.append("<row>" + "".join(cell(c, n, v) for c, v in zip(cols, row)) + "</row>")
    xml_rows.append('<row><c r="A99" t="inlineStr"><is><t>Disclaimer :</t></is></c></row>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet><sheetData>{''.join(xml_rows)}</sheetData></worksheet>")
    return buf.getvalue()


NEW = ["NSDL Scheme Code", "Scheme Name", "Scheme Type", "Scheme Category", "TER Date", "Regular Plan - Base Expense Ratio (BER)",
       "Regular Plan - Total TER (%)", "Direct Plan - Base Expense Ratio (BER)", "Direct Plan - Total TER (%)"]
OLD = ["NSDL Scheme Code", "Scheme Name", "Scheme Type", "Scheme Category", "TER Date", "Regular Plan - Base TER (%)",
       "Regular Plan - Additional expense b (%)", "Regular Plan - GST (%)", "Regular Plan - Total TER (%)", "Direct Plan - Base TER (%)",
       "Direct Plan - Total TER (%)"]


def test_ter_file_new_and_old_layouts():
    new = amfi_ter.parse_ter_xlsx(_xlsx(NEW, [["X/1", "Parag Parikh Flexi Cap Fund", "Open Ended", "Equity", 46266, 1.2, 1.31, 0.6, 0.69],
                                            ["X/1", "Parag Parikh Flexi Cap Fund", "Open Ended", "Equity", 46294, 1.2, 1.31, 0.6, 0.69]]))
    latest = amfi_ter.latest_per_scheme(new)
    t = latest["paragparikhflexicapfund"]
    assert t.ter_date == date(2026, 9, 29) and t.direct_ter == pytest.approx(0.0069) and t.regular_ter == pytest.approx(0.0131)
    assert t.direct_fee == pytest.approx(0.006) and t.regular_fee == pytest.approx(0.012)  # the fund house's own part
    old = amfi_ter.parse_ter_xlsx(_xlsx(OLD, [["X/2", "Old Fund", "Open Ended", "Debt", 46000, 1, 0.1, 0.2, 1.3, 0.2, 0.4]]))
    assert old[0].direct_ter == pytest.approx(0.004) and old[0].regular_ter == pytest.approx(0.013)


# ------------------------------------------------------------------ scoring service + plan (synthetic funds)
def _add_fund(db, code, name, category, asset_class="Equity", growth=0.12, seed=0, twin=None):
    s = MfScheme(scheme_code=code, fund_name=name, display_name=f"{name} - Direct Plan - Growth", plan="direct", option="growth",
                 scheme_type="Open Ended Schemes", asset_class=asset_class, category=category, is_active=True, tracked=True,
                 latest_nav_date=date(2026, 9, 29), history_synced_at=utcnow(), history_start=date(2018, 1, 1), twin_scheme_code=twin)
    db.add(s)
    db.flush()
    ser = _series(years=8, growth=growth, seed=seed, vol=0.01)
    db.bulk_insert_mappings(NavDaily, [{"scheme_code": code, "date": d.date(), "nav": float(v)} for d, v in ser.items()])
    db.add(MfSchemeFacts(scheme_code=code, as_of=date(2026, 9, 1), ter=0.005 + seed / 1000))


@pytest.fixture
def universe():
    with SessionLocal() as db:
        for i in range(6):
            _add_fund(db, 1000 + i, f"Flexi {i}", "Flexi Cap Fund", growth=0.10 + i / 100, seed=i)
            _add_fund(db, 2000 + i, f"AMC{i} Nifty 50 Index Fund", "Index Fund – Equity", "Index", growth=0.11, seed=10 + i)
            _add_fund(db, 3000 + i, f"Liquid {i}", "Liquid Fund", "Debt", growth=0.065, seed=20 + i)
            _add_fund(db, 4000 + i, f"BAF {i}", "Balanced Advantage", "Hybrid", growth=0.09 + i / 200, seed=30 + i)
            _add_fund(db, 5000 + i, f"Short {i}", "Short Duration Fund", "Debt", growth=0.07, seed=40 + i)
        db.commit()
    yield


def test_run_scoring_end_to_end(universe):
    with SessionLocal() as db:
        msg = mf_scores.run_scoring(db)
        assert "Scored" in msg
        top = mf_scores.top_in(db, category="Flexi Cap Fund")
        assert top[0][0].scheme_code == 1005  # fastest-growing flexi fund
        # Flexi-cap's stand-in is a Nifty 500 index fund; there isn't one here, so "beat the index" is not applicable
        assert "beat_bench_3y" not in top[0][1].metrics_json and "beat_bench_3y" not in top[0][1].components_json
        assert top[0][1].coverage == pytest.approx(73 / 83, abs=0.01)  # 83 applicable points; tenure + AUM (10) have no data yet
        idx = mf_scores.top_in(db, index_group_label="Nifty 50")
        assert len(idx) == 6 and idx[0][1].model == "index"
        assert mf_scores.top_in(db, category="Liquid Fund")[0][1].model == "liquid"


def test_plan_for_a_conservative_saver(universe, signed_in):
    with SessionLocal() as db:
        mf_scores.run_scoring(db)
        user = db.query(User).one()
        profile_svc.save_profile(db, user, ProfileAnswers(age=34, income_range="1lto2l", monthly_expenses=20000, monthly_investable=30000,
                                                         emergency_savings=200000, monthly_emi=0, horizon="5plus", fall_reaction="sell", experience="none"))
        db.add(Goal(user_id=user.id, name="House", goal_type="house", target_amount_today=1_000_000, inflation_rate=0.06, target_year=utcnow().year + 8))
        db.add(Goal(user_id=user.id, name="Trip", goal_type="travel", target_amount_today=100_000, inflation_rate=0.06, target_year=utcnow().year + 1))
        db.commit()
    p = signed_in.get("/api/plan").json()
    assert p["profile"] == "conservative" and p["emergency"] is None  # 10 months saved → no emergency step
    house, trip = sorted(p["goals"], key=lambda g: -g["years_away"])
    assert house["allocation"] == load_rules("plan")["templates"]["conservative"]
    assert trip["allocation"] == {"liquid": 100}  # under a year to mid-next-year
    assert house["recommended_sip"] >= house["sip_needed"]["conservative"] >= house["sip_needed"]["optimistic"]
    assert all(f["fund"] for f in house["funds"])
    assert p["budget"]["for_mutual_funds"] == 27000  # 90% of ₹30,000 (trading 0%, stocks 10%)
    assert sum(s["monthly_affordable"] for s in p["sips"]) <= 27000
    calc = signed_in.post("/api/plan/sip-calculator", json={"monthly": 10000, "years": 10}, headers=CSRF).json()
    cons, exp, opt = (s["value"] for s in calc["scenarios"])
    assert cons < exp < opt and calc["scenarios"][0]["invested"] == 1_200_000
    assert signed_in.post("/api/plan/sip-calculator", json={"monthly": 1, "years": 1, "mix": {"gold": 100}}, headers=CSRF).status_code == 400
    scores = signed_in.get("/api/mf/scores", params={"category": "Flexi Cap Fund"}).json()
    assert scores[0]["score"]["rank"] == 1
    page = signed_in.get("/api/mf/schemes/1005").json()
    assert page["scoring"]["rank"] == 1 and page["scoring"]["components"]


def test_plan_needs_scores(signed_in):
    assert signed_in.get("/api/plan").status_code == 409
