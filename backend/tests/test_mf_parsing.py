from datetime import date

import pytest

from app.connectors import amfi, mfapi
from app.connectors.http import SourceUnavailable
from app.engines import mf_catalog as c
from app.rules import load_rules
from tests import mf_fixtures as fx

RULES = load_rules("mf_categories")


def test_nav_all_parses_rows_and_sections():
    rows = {r.scheme_code: r for r in amfi.parse_nav_all(fx.nav_all())}
    assert len(rows) == 8
    p = rows[122639]
    assert (p.plan_raw, p.option_raw, p.nav, p.nav_date) == ("Direct Plan", "Growth", 90.5, date(2026, 9, 29))
    assert p.raw_category == "Equity Schemes - Flexi Cap Fund" and p.scheme_type == "Open Ended Schemes"
    assert rows[120504].isin_reinvest == "INF846K01EY8"
    assert rows[120504].isin_growth == "INF846K01EX0"
    assert rows[140001].scheme_type == "Close Ended Schemes"
    assert rows[130947].nav_date == date(2020, 4, 24)


def test_zero_nav_is_treated_as_missing():
    rows = amfi.parse_nav_all(fx.nav_all(ppfas_d="0"))
    assert next(r for r in rows if r.scheme_code == 122639).nav is None


def test_format_change_is_detected():
    with pytest.raises(SourceUnavailable):
        amfi.parse_nav_all("Scheme Code;ISIN;Scheme Name;Net Asset Value;Date\n1;x;y;1;29-Sep-2026")
    with pytest.raises(SourceUnavailable):
        amfi.parse_scheme_master("Code,Name\n1,x")


def test_scheme_master_splits_joined_isins():
    rows = {r.scheme_code: r for r in amfi.parse_scheme_master(fx.MASTER)}
    assert rows[120504].isin_growth == "INF846K01EX0" and rows[120504].isin_reinvest == "INF846K01EY8"
    assert rows[122639].launch_date == date(2013, 5, 24)
    assert rows[122639].nav_name == "Parag Parikh Flexi Cap Fund - Direct Plan - Growth"


def test_nav_history_report():
    rows = amfi.parse_nav_history(fx.nav_history([(122639, "24-Sep-2026", 89.1), (122639, "25-Sep-2026", 89.4)]))
    assert [(r.nav_date, r.nav) for r in rows] == [(date(2026, 9, 24), 89.1), (date(2026, 9, 25), 89.4)]
    assert rows[0].raw_category == "Equity Schemes - Flexi Cap Fund"


def test_mfapi_history_sorted_and_cleaned():
    payload = {
        "status": "SUCCESS",
        "data": [{"date": "29-09-2026", "nav": "29.7872"}, {"date": "bad", "nav": "1"}, {"date": "14-12-2015", "nav": "10.0171"}],
    }
    assert mfapi.parse_history(payload) == [(date(2015, 12, 14), 10.0171), (date(2026, 9, 29), 29.7872)]
    with pytest.raises(SourceUnavailable):
        mfapi.parse_history({"status": "FAIL"})


@pytest.mark.parametrize(
    "raw,name,stype,expected",
    [
        ("Equity Schemes - Flexi Cap Fund", "X", "Open Ended Schemes", ("Equity", "Flexi Cap Fund")),
        ("Equity Scheme - Flexi Cap Fund", "X", "Open Ended Schemes", ("Equity", "Flexi Cap Fund")),
        ("Equity Schemes - ELSS- Tax Saver Fund", "X", "Open Ended Schemes", ("Equity", "ELSS")),
        ("Equity Scheme - ELSS", "X", "Open Ended Schemes", ("Equity", "ELSS")),
        ("Hybrid Schemes - Balanced Advantage Fund/ Dynamic Asset Allocation", "X", "Open Ended Schemes", ("Hybrid", "Balanced Advantage")),
        ("Hybrid Scheme - Dynamic Asset Allocation or Balanced Advantage", "X", "Open Ended Schemes", ("Hybrid", "Balanced Advantage")),
        ("Income/Debt Oriented Schemes - Short Term Fund", "X", "Open Ended Schemes", ("Debt", "Short Duration Fund")),
        ("Debt Scheme - Short Duration Fund", "X", "Open Ended Schemes", ("Debt", "Short Duration Fund")),
        ("Income/Debt Oriented Schemes - Sectoral Fund", "X", "Open Ended Schemes", ("Debt", "Sectoral Debt Fund")),
        ("Index Funds - Equity Funds", "X", "Open Ended Schemes", ("Index", "Index Fund – Equity")),
        ("Other Scheme - Index Funds", "UTI Nifty 50 Index Fund", "Open Ended Schemes", ("Index", "Index Fund – Equity")),
        ("Other Scheme - Index Funds", "UTI CRISIL SDL Maturity June 2027 Index Fund", "Open Ended Schemes", ("Index", "Index Fund – Debt")),
        ("Other Scheme - Other  ETFs", "X", "Open Ended Schemes", ("ETF", "Other ETF")),
        ("Children’s Fund - Childrens' Fund", "X", "Open Ended Schemes", ("Solution", "Children's Fund")),
        ("Growth", "X", "Open Ended Schemes", ("Legacy", "Growth")),
        ("Income/Debt Oriented Schemes - Fixed Term Plan", "X", "Close Ended Schemes", ("Closed/Interval", "Income/Debt Oriented Schemes - Fixed Term Plan")),
    ],
)
def test_categories_normalised(raw, name, stype, expected):
    cat = c.categorise(raw, name, stype, RULES)
    assert (cat.asset_class, cat.category) == expected


def test_plan_and_option():
    assert c.plan_of("Direct Plan") == "direct"
    assert c.plan_of("", "Axis Fund - Regular Growth") == "regular"
    assert c.plan_of("", "Some Liquid Fund - Retail Plan - Growth") == "unknown"
    assert c.option_of("Growth Option") == ("growth", "Growth")
    assert c.option_of("Monthly IDCW") == ("idcw", "Monthly IDCW")
    assert c.option_of("", "X Fund - Direct Plan - Dividend Payout")[0] == "idcw"
    assert c.option_of("", "X Fund - Bonus")[0] == "bonus"


def test_variant_key_links_direct_and_regular_but_not_lock_in_variants():
    k = lambda n: c.variant_key("Axis AMC", n)  # noqa: E731
    assert k("Axis Children's Fund - Lock in - Direct Growth") == k("Axis Children's Fund - Lock in - Regular Growth")
    assert k("Axis Children's Fund - Lock in - Direct Growth") != k("Axis Children's Fund - No Lock in - Direct Growth")
    assert k("PP Flexi Cap Fund - Direct Plan - Growth") == k("PP Flexi Cap Fund - Regular Plan - Growth")
