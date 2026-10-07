from datetime import date, timedelta

import pytest

from app.engines import mf_returns as r


def series_growing(start: date, days: int, yearly: float) -> list[tuple[date, float]]:
    return [(start + timedelta(days=i), 10 * (1 + yearly) ** (i / 365.25)) for i in range(0, days + 1) if (start + timedelta(days=i)).weekday() < 5]


def test_cagr_matches_constant_growth():
    s = series_growing(date(2016, 1, 4), 3650, 0.12)
    out = r.summary(s)
    assert out["1y"] == pytest.approx(0.12, abs=0.003)
    assert out["5y"] == pytest.approx(0.12, abs=0.002)
    assert out["since_start"] == pytest.approx(0.12, abs=0.001)
    assert out["10y"] is None  # just short of 10 years


def test_not_enough_history():
    s = series_growing(date(2025, 1, 1), 400, 0.1)
    assert r.trailing(s, 3) is None and r.trailing(s, 1) is not None
    assert r.summary([])["1y"] is None


def test_start_date_on_a_holiday_uses_previous_nav():
    s = [(date(2025, 9, 26), 10.0), (date(2026, 9, 29), 11.0)]  # nothing on 29-Sep-2025
    assert r.trailing(s, 1) == pytest.approx(1.1 ** (365.25 / 368) - 1)  # 368 days, annualised


def test_downsample_keeps_last_point_per_week():
    s = series_growing(date(2016, 1, 4), 3650, 0.1)
    d = r.downsample_weekly(s)
    assert len(d) < 700 and d[-1] == s[-1]
    assert r.downsample_weekly(s[:100]) == s[:100]
